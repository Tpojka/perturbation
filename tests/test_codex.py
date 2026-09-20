import os
from pathlib import Path

from perturbation.agents import codex
from perturbation.agents.base import ConfigError
from perturbation.install import system
from tests.support import IsolatedTestCase, read_json, write_json

COMMANDS = system.Commands(Path("/data/perturbation.pyz")).for_agent("codex")
COMMAND = COMMANDS.hook()
FOREIGN = {"type": "command", "command": "say done"}


class CodexHooksTest(IsolatedTestCase):
    def commands(self, event):
        return [h["command"] for g in read_json(codex.hooks_path())["hooks"].get(event, []) for h in g["hooks"]]

    def test_location_and_detect(self):
        self.assertEqual(codex.hooks_path(), Path(self.home) / ".codex" / "hooks.json")
        self.assertIsNone(codex.detect())
        os.environ["CODEX_HOME"] = os.path.join(self.home, "elsewhere")
        self.assertEqual(codex.hooks_path(), Path(self.home) / "elsewhere" / "hooks.json")
        os.makedirs(codex.codex_home())
        self.assertEqual(codex.detect(), "found ~/elsewhere")

    def test_registers_every_event_without_matchers(self):
        codex.install(COMMANDS)
        hooks = read_json(codex.hooks_path())["hooks"]
        self.assertEqual(set(hooks), set(codex.EVENTS))
        self.assertEqual(hooks["Stop"], [{"hooks": [{"type": "command", "command": COMMAND, "timeout": 5}]}])
        for event in codex.SHORT_EVENTS:
            self.assertEqual(hooks[event][0]["hooks"][0]["timeout"], 3)

    def test_only_known_top_level_keys(self):
        # Codex rejects the whole file if it has keys other than "description" and "hooks".
        write_json(codex.hooks_path(), {"description": "mine"})
        codex.install(COMMANDS)
        self.assertEqual(set(read_json(codex.hooks_path())), {"description", "hooks"})

    def test_keeps_other_hooks(self):
        write_json(codex.hooks_path(), {"hooks": {"Stop": [{"hooks": [FOREIGN]}]}})
        codex.install(COMMANDS)
        self.assertEqual(self.commands("Stop"), ["say done", COMMAND])

    def test_reinstall_changes_nothing_so_trust_is_kept(self):
        self.assertTrue(codex.changed(COMMANDS))
        codex.install(COMMANDS)
        before = codex.hooks_path().read_text()
        self.assertFalse(codex.changed(COMMANDS))
        codex.install(COMMANDS)
        self.assertEqual(codex.hooks_path().read_text(), before)

    def test_reinstall_keeps_positions(self):
        # Codex remembers trust per position, so neither our hook nor the user's may move.
        codex.install(COMMANDS)
        data = read_json(codex.hooks_path())
        data["hooks"]["Stop"].append({"hooks": [FOREIGN]})
        write_json(codex.hooks_path(), data)
        moved = system.Commands(Path("/new/perturbation.pyz")).for_agent("codex")
        self.assertTrue(codex.changed(moved))
        codex.install(moved)
        self.assertEqual(self.commands("Stop"), [moved.hook(), "say done"])

    def test_duplicates_are_removed(self):
        write_json(codex.hooks_path(), {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": COMMAND}]}] * 2}})
        codex.install(COMMANDS)
        self.assertEqual(self.commands("Stop"), [COMMAND])

    def test_uninstall_removes_only_ours(self):
        write_json(codex.hooks_path(), {"hooks": {"Stop": [{"hooks": [FOREIGN]}]}})
        codex.install(COMMANDS)
        codex.uninstall()
        self.assertEqual(read_json(codex.hooks_path()), {"hooks": {"Stop": [{"hooks": [FOREIGN]}]}})
        self.assertTrue(os.path.exists(str(codex.hooks_path()) + ".perturbation.bak"))

    def test_uninstall_removes_a_file_that_only_held_ours(self):
        codex.install(COMMANDS)
        self.assertEqual(codex.installed(), f"{len(codex.EVENTS)} hook entries in ~/.codex/hooks.json")
        codex.uninstall()
        self.assertFalse(codex.hooks_path().exists())
        codex.uninstall()  # nothing to do, and no file is created
        self.assertFalse(codex.hooks_path().exists())

    def test_predecessor_entries(self):
        old = 'python3 "/data/codexalgia.pyz" hook'
        write_json(codex.hooks_path(), {"hooks": {"Stop": [{"hooks": [FOREIGN, {"type": "command", "command": old}]}]}})
        self.assertIsNone(codex.installed())
        self.assertEqual(codex.installed(("codexalgia.pyz",)), "1 hook entries in ~/.codex/hooks.json")
        codex.uninstall(("codexalgia.pyz",))
        self.assertEqual(self.commands("Stop"), ["say done"])

    def test_invalid_json_is_left_untouched(self):
        codex.hooks_path().parent.mkdir(parents=True)
        codex.hooks_path().write_text("{ not json")
        with self.assertRaises(ConfigError):
            codex.install(COMMANDS)
        self.assertEqual(codex.hooks_path().read_text(), "{ not json")

    def test_doctor(self):
        codex.install(COMMANDS)
        self.assertTrue(all(c.ok for c in codex.doctor(COMMANDS)))
        (codex.codex_home() / "config.toml").write_text("[features]\nhooks = false\n")
        self.assertIn("turned off", next(c.text for c in codex.doctor(COMMANDS) if not c.ok))


class HooksDisabledTest(IsolatedTestCase):
    def config(self, text):
        path = codex.codex_home() / "config.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def test_default_is_enabled(self):
        self.assertFalse(codex.hooks_disabled())
        self.config('model = "gpt-5"\n[hooks]\nhooks = false\n')
        self.assertFalse(codex.hooks_disabled())

    def test_feature_flag_turns_hooks_off(self):
        for text in ("[features]\nhooks = false\n", "[ features ]\ncodex_hooks=false # old name\n", "features.hooks = false\n"):
            self.config(text)
            self.assertTrue(codex.hooks_disabled(), text)
        self.config("[features]\nhooks = true\n")
        self.assertFalse(codex.hooks_disabled())


class CodexParseTest(IsolatedTestCase):
    def parse(self, event, **fields):
        return codex.parse(None, {"hook_event_name": event, "session_id": "abc", "cwd": "/work/project", **fields})

    def test_states(self):
        self.assertEqual(self.parse("SessionStart").state, "ready")
        for event in ("UserPromptSubmit", "PreToolUse", "PostToolUse"):
            self.assertEqual(self.parse(event).state, "busy")
        self.assertEqual(self.parse("Interrupt").state, "ready")
        self.assertIsNone(self.parse("Interrupt").notice)
        self.assertEqual(self.parse("SessionEnd").state, None)
        self.assertIsNone(self.parse("SubagentStop"))

    def test_stop_summarises_the_last_message(self):
        self.assertEqual(self.parse("Stop", last_assistant_message="- **Done**: `x`\nmore").notice, ("ready", "Done: x"))
        self.assertEqual(self.parse("Stop").notice.message, "Task finished")

    def test_permission_request_waits_with_a_grace_period(self):
        update = self.parse("PermissionRequest", tool_name="Bash", tool_input={"command": ["git", "push"]})
        self.assertEqual((update.state, update.delay), ("waiting", codex.APPROVAL_GRACE_SECONDS))
        self.assertEqual(update.notice, ("needs_you", "Wants to run: git push"))
        self.assertEqual(self.parse("PermissionRequest", tool_name="apply_patch").notice.message, "Wants to edit files")
        self.assertEqual(self.parse("PermissionRequest", tool_name="web_search").notice.message, "Wants to use web_search")
        self.assertEqual(self.parse("PermissionRequest").notice.message, "Wants to use a tool")
