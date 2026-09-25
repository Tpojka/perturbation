import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout
from unittest import mock

from perturbation import agents, config, install, paths, state
from perturbation.agents import antigravity, claude, codex
from perturbation.install import system
from tests.support import BUSY, IsolatedTestCase, read_json, shells, write_json
from tests.test_host import read_message


class InstallerTestCase(IsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(system.unregister_host)

    def run_installer(self, *args):
        with redirect_stdout(io.StringIO()) as out:
            install.main(list(args))
        return out.getvalue()


class InstallTest(InstallerTestCase):
    def test_exit_installs_nothing(self):
        self.assertIn("Nothing installed", self.run_installer("3"))
        self.assertFalse(os.path.exists(self.data))
        self.assertFalse(claude.settings_path().exists())

    def test_install_is_self_contained_and_works(self):
        out = self.run_installer("2", "--all")
        self.assertTrue(paths.app_file().is_file())
        self.assertTrue((paths.extension_dir() / "manifest.json").is_file())
        for lamp in ("red", "amber", "green", "grey"):
            self.assertTrue(paths.icon(f"lamp-{lamp}").is_file(), lamp)
        self.assertFalse(list(paths.extension_dir().rglob("*.svg")))
        settings = config.load()
        self.assertEqual((settings["notifications"], settings["sound"], settings["agents"], settings["order"]), (True, True, agents.ids(), agents.ids()))
        for adapter in agents.registered():
            self.assertTrue(adapter.installed(), adapter.ID)
            self.assertIn(adapter.NAME, out)
        self.assertIn("/hooks inside Codex", out)

        # The installed app runs on its own: a hook event is recorded as session state.
        for adapter in agents.registered():
            event, payload = BUSY[adapter.ID]
            argv = [sys.executable, str(paths.app_file()), "hook", adapter.ID] + ([event] if event else [])
            subprocess.run(argv, input=json.dumps(payload).encode(), check=True, cwd=self.home)
            self.assertEqual(state.current(adapter.ID, "s1")[0], "busy", adapter.ID)

    def test_hook_commands_run_in_the_shell_and_never_fail(self):
        self.run_installer("1", "--all")
        commands = system.Commands(paths.app_file())
        for adapter in agents.registered():
            event, payload = BUSY[adapter.ID]
            shell = getattr(adapter, "SHELL", None)
            if adapter.SHAPE != "config":
                continue  # a plugin file runs no shell command of ours
            command = commands.hook(adapter.ID, event, shell)
            for argv in shells(command, shell):
                with self.subTest(agent=adapter.ID, shell=argv[0]):
                    state.clear(adapter.ID, "s1")
                    result = subprocess.run(argv, input=json.dumps(payload).encode(), cwd=self.home, capture_output=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    # Some agents read a hook's stdout as a decision, so anything here could deny a tool call.
                    self.assertEqual(result.stdout.strip(), b"")
                    self.assertEqual(state.current(adapter.ID, "s1")[0], "busy")

        # Python exits 2 without the app, and a failing PreToolUse hook could gate every tool call.
        paths.app_file().unlink()
        for adapter in agents.registered():
            event, payload = BUSY[adapter.ID]
            shell = getattr(adapter, "SHELL", None)
            if adapter.SHAPE != "config":
                continue
            for argv in shells(commands.hook(adapter.ID, event, shell), shell):
                with self.subTest(agent=adapter.ID, shell=argv[0], app="missing"):
                    result = subprocess.run(argv, input=json.dumps(payload).encode(), cwd=self.home, capture_output=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), b"")

    def test_statusline_command_prints_exactly_one_line(self):
        self.run_installer("1", "--agents", "antigravity")
        command = system.Commands(paths.app_file()).statusline("antigravity")
        payload = json.dumps({"conversation_id": "s1", "agent_state": "working", "cwd": "/work/project"}).encode()
        for argv in shells(command):
            with self.subTest(shell=argv[0]):
                result = subprocess.run(argv, input=payload, cwd=self.home, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "perturbation · working\n".encode("utf-8"))
        for argv in shells(command):
            with self.subTest(shell=argv[0], input="garbage"):
                result = subprocess.run(argv, input=b"not json", cwd=self.home, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, b"\n")

    def test_agents_flag(self):
        self.run_installer("1", "--agents", "codex,claude")
        self.assertEqual(config.load()["agents"], ["claude", "codex"])
        self.assertTrue(claude.installed() and codex.installed())
        self.assertIsNone(agents.get("copilot").installed())
        self.run_installer("1", "--agents=antigravity")
        self.assertEqual(config.load()["agents"], ["antigravity"])
        self.assertIsNone(claude.installed())  # dropped agents lose their hooks
        with self.assertRaises(SystemExit):
            self.run_installer("1", "--agents", "claude,nobody")

    def test_default_agents_are_the_detected_ones(self):
        os.makedirs(codex.codex_home())
        self.run_installer("2")
        self.assertEqual(config.load()["agents"], ["codex"])
        self.assertFalse(os.path.exists(str(self.data)) is False)

    def test_menu_toggles_agents_and_asks_the_extra_questions(self):
        os.makedirs(claude.config_home())
        os.makedirs(antigravity.cli_home())
        # claude and antigravity are pre-checked; "1" unchecks claude, "3" checks copilot, Enter confirms.
        with mock.patch("builtins.input", side_effect=["1 3", "", "", "2", "n", "y"]) as ask:
            out = self.run_installer()
        self.assertIn("[x] 1) Claude Code", out)
        self.assertIn("found ~/.claude", out)
        self.assertIn("[ ] 2) Codex CLI", out)
        self.assertIn("not found", out)
        questions = " ".join(call.args[0] for call in ask.call_args_list)
        self.assertIn("Play a sound with notifications? [Y/n]", questions)
        self.assertIn('Let Antigravity show "needs you" alerts?', questions)
        self.assertIn("[y/N]", questions)  # the status line is opt-in
        settings = config.load()
        self.assertEqual((settings["agents"], settings["notifications"], settings["sound"], settings["statusline"]), (["copilot", "antigravity"], True, False, {"antigravity": True}))
        self.assertEqual(antigravity.statusline_owner(), "ours")

        # Option 1 is the extension alone, so neither extra question is asked; the watched set is kept.
        with mock.patch("builtins.input", side_effect=["", "", "1"]) as ask:
            self.run_installer()
        self.assertEqual(ask.call_count, 3)
        self.assertEqual(config.load()["agents"], ["copilot", "antigravity"])
        self.assertIsNone(antigravity.statusline_owner())  # option 1 has no notifier, so no status line

    def test_menu_shortcuts_and_backing_out(self):
        with mock.patch("builtins.input", side_effect=["a", "", "", "3"]):
            self.run_installer()
        self.assertFalse(os.path.exists(self.data))
        with mock.patch("builtins.input", side_effect=["a", "n", "2", "", "", "1"]):
            self.run_installer()
        self.assertEqual(config.load()["agents"], ["codex"])
        with mock.patch("builtins.input", side_effect=EOFError):
            self.assertIn("Nothing installed", self.run_installer())

    def test_the_status_line_is_off_unless_asked_for(self):
        self.run_installer("2", "--agents", "antigravity")
        self.assertIsNone(antigravity.statusline_owner())
        self.run_installer("2", "--agents", "antigravity", "--statusline")
        self.assertEqual(antigravity.statusline_owner(), "ours")
        self.assertEqual(config.load()["statusline"], {"antigravity": True})

    def test_an_existing_status_line_is_never_overwritten(self):
        mine = {"statusLine": {"type": "command", "command": "~/my-own-line.sh"}}
        write_json(antigravity.settings_path(), mine)
        out = self.run_installer("2", "--agents", "antigravity", "--statusline")
        self.assertIn("left it alone", out)
        self.assertIn("statusline antigravity", out)  # the command to set by hand
        self.assertEqual(read_json(antigravity.settings_path()), mine)
        self.assertEqual(config.load()["statusline"], {})
        # And it isn't even offered in the menu.
        os.makedirs(antigravity.cli_home(), exist_ok=True)
        with mock.patch("builtins.input", side_effect=["", "", "2", "y"]) as ask:
            self.run_installer()
        self.assertEqual(ask.call_count, 4)

    def test_statusline_command_turns_it_on_and_off(self):
        self.run_installer("2", "--agents", "antigravity")
        self.assertIn("status line on", self.run_installer("statusline", "antigravity", "on"))
        self.assertEqual(antigravity.statusline_owner(), "ours")
        self.assertIn("status line removed", self.run_installer("statusline", "antigravity", "off"))
        self.assertIsNone(antigravity.statusline_owner())
        for bad in (("statusline", "antigravity", "maybe"), ("statusline", "claude", "on"), ("statusline",)):
            with self.assertRaises(SystemExit):
                self.run_installer(*bad)

    def test_sound_flag_and_set_commands(self):
        self.run_installer("2", "--agents", "claude", "--no-sound")
        self.assertFalse(config.load()["sound"])
        self.assertIn("Sound on", self.run_installer("set", "sound", "on"))
        self.assertTrue(config.load()["sound"])
        self.run_installer("set", "notifications", "off")
        self.assertFalse(config.load()["notifications"])
        self.run_installer("set", "waiting-as-busy", "on")
        self.assertTrue(config.load()["count_waiting_as_busy"])
        self.assertIn("muted", self.run_installer("mute", "claude", "on"))
        self.assertEqual(config.load()["mute"], {"claude": True})
        self.run_installer("mute", "claude", "off")
        self.assertEqual(config.load()["mute"], {})
        for bad in (("set", "volume", "on"), ("set", "sound", "loud"), ("mute", "nobody", "on"), ("set",)):
            with self.assertRaises(SystemExit):
                self.run_installer(*bad)

    def test_set_agents_adds_and_removes_hooks(self):
        self.run_installer("1", "--agents", "claude")
        self.run_installer("set", "agents", "claude,codex")
        self.assertEqual(config.load()["agents"], ["claude", "codex"])
        self.assertTrue(codex.installed())
        self.run_installer("set", "agents", "codex")
        self.assertEqual(config.load()["agents"], ["codex"])
        self.assertIsNone(claude.installed())
        with self.assertRaises(SystemExit):
            self.run_installer("set", "agents", "nobody")

    def test_set_requires_an_install(self):
        for args in (("set", "sound", "on"), ("set", "agents", "claude"), ("mute", "claude", "on"), ("statusline", "antigravity", "on")):
            with self.assertRaises(SystemExit):
                self.run_installer(*args)

    def test_option_1_turns_notifier_off(self):
        self.run_installer("2", "--agents", "claude")
        self.run_installer("1", "--agents", "claude")
        self.assertFalse(config.load()["notifications"])

    def test_a_broken_config_file_stops_that_agent_not_the_install(self):
        claude.settings_path().parent.mkdir(parents=True)
        claude.settings_path().write_text("{ not json", encoding="utf-8")
        out = self.run_installer("1", "--agents", "claude,codex")
        self.assertIn("not valid JSON", out)
        self.assertTrue(paths.app_file().is_file())
        self.assertEqual(claude.settings_path().read_text(), "{ not json")
        self.assertEqual(config.load()["agents"], ["codex"])

    def test_no_agents_selected_still_installs_the_lamp(self):
        out = self.run_installer("1", "--agents=")
        self.assertIn("lamp stays grey", out)
        self.assertEqual(config.load()["agents"], [])

    def test_status_reports_everything(self):
        self.run_installer("2", "--agents", "claude,antigravity", "--statusline")
        self.run_installer("mute", "claude", "on")
        state.set_state("claude", "s1", state.BUSY)
        out = self.run_installer("status")
        self.assertIn("Perturbation", out)
        self.assertIn("✓ Google Chrome    registered", out)
        self.assertIn("● Claude Code", out)
        self.assertIn("1 working of 1 session, muted", out)
        self.assertIn("status line on", out)
        self.assertIn("· Codex CLI", out)
        self.assertIn("not watched", out)

    def test_uninstall_removes_everything(self):
        self.run_installer("2", "--all", "--statusline")
        write_json(codex.hooks_path(), {**read_json(codex.hooks_path()), "description": "mine"})
        self.run_installer("uninstall")
        self.assertFalse(os.path.exists(self.data))
        for adapter in agents.registered():
            self.assertIsNone(adapter.installed(), adapter.ID)
        self.assertIsNone(antigravity.statusline_owner())
        self.assertEqual(read_json(codex.hooks_path()), {"description": "mine"})
        self.assertFalse(system.registered_manifests())

    def test_chrome_can_start_the_registered_host(self):
        self.run_installer("1", "--agents", "claude")
        (manifest_path,) = system.registered_manifests()
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(manifest["name"], "com.tpojka.perturbation")
        self.assertEqual(manifest["allowed_origins"], ["chrome-extension://jbibmafopagpblieglanmabkegglkpgo/"])
        # Chrome runs the manifest's path with the extension origin as the argument.
        proc = subprocess.Popen([manifest["path"], "chrome-extension://test/"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        try:
            message = read_message(proc.stdout)
            self.assertEqual((message["type"], message["overall"]), ("status", "ready"))
            proc.stdin.close()
            self.assertEqual(proc.wait(timeout=10), 0)
        finally:
            proc.kill()
            proc.stdout.close()

    def test_installed_app_version(self):
        self.run_installer("1", "--agents", "claude")
        result = subprocess.run([sys.executable, str(paths.app_file()), "version"], capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), install.__version__)
        self.assertNotEqual(subprocess.run([sys.executable, str(paths.app_file())], capture_output=True).returncode, 0)
