import os
from pathlib import Path

from perturbation.agents import antigravity
from perturbation.agents.base import ConfigError
from perturbation.install import system
from tests.support import IsolatedTestCase, read_json, write_json

COMMANDS = system.Commands(Path("/data/perturbation.pyz")).for_agent("antigravity")
STATUSLINE = COMMANDS.statusline()

# Another bundle in the same file, and settings the CLI wrote itself. Neither may be disturbed.
FOREIGN_BUNDLE = {"my-linter-hook": {"PostToolUse": [{"matcher": "run_command", "hooks": [{"command": "./lint.sh"}]}]}}
FOREIGN_SETTINGS = {"permissions": {"allow": ["command(agy)"]}, "trustedWorkspaces": ["/home/u"]}


class HooksFileTest(IsolatedTestCase):
    def test_locations_and_detect(self):
        self.assertEqual(antigravity.hooks_path(), Path(self.home) / ".gemini" / "config" / "hooks.json")
        self.assertEqual(antigravity.settings_path(), Path(self.home) / ".gemini" / "antigravity-cli" / "settings.json")
        self.assertIsNone(antigravity.detect())
        os.makedirs(antigravity.cli_home())
        self.assertEqual(antigravity.detect(), "found ~/.gemini/antigravity-cli")

    def test_registers_every_event_under_one_bundle(self):
        antigravity.install(COMMANDS)
        bundle = read_json(antigravity.hooks_path())["perturbation"]
        self.assertEqual(set(bundle), {"PreInvocation", "PostInvocation", "Stop", "PreToolUse", "PostToolUse"})
        for event in ("PreToolUse", "PostToolUse"):
            (group,) = bundle[event]
            self.assertEqual(group["matcher"], ".*")
            self.assertEqual(group["hooks"], [{"type": "command", "command": COMMANDS.hook("busy"), "timeout": 5}])
        for event in ("PreInvocation", "PostInvocation"):
            self.assertEqual(bundle[event], [{"type": "command", "command": COMMANDS.hook("busy"), "timeout": 5}])
        # The payload carries no event name, so Stop has to be told which event it is.
        self.assertEqual(bundle["Stop"], [{"type": "command", "command": COMMANDS.hook("stop"), "timeout": 5}])
        self.assertIn("hook antigravity stop", COMMANDS.hook("stop"))
        self.assertEqual(antigravity.installed(), "bundle 'perturbation' in ~/.gemini/config/hooks.json")

    def test_keeps_other_bundles_and_backs_the_file_up(self):
        write_json(antigravity.hooks_path(), FOREIGN_BUNDLE)
        antigravity.install(COMMANDS)
        self.assertEqual(read_json(antigravity.hooks_path())["my-linter-hook"], FOREIGN_BUNDLE["my-linter-hook"])
        self.assertEqual(read_json(str(antigravity.hooks_path()) + ".perturbation.bak"), FOREIGN_BUNDLE)

    def test_uninstall_removes_only_our_bundle(self):
        write_json(antigravity.hooks_path(), {**FOREIGN_BUNDLE, "antigravalgia": {"Stop": []}})
        antigravity.install(COMMANDS)
        antigravity.uninstall()
        antigravity.uninstall()  # twice is harmless
        self.assertEqual(read_json(antigravity.hooks_path()), {**FOREIGN_BUNDLE, "antigravalgia": {"Stop": []}})
        self.assertEqual(antigravity.installed(("antigravalgia.pyz",)), "bundle 'antigravalgia' in ~/.gemini/config/hooks.json")
        antigravity.uninstall(("antigravalgia.pyz",))
        self.assertEqual(read_json(antigravity.hooks_path()), FOREIGN_BUNDLE)

    def test_an_unreadable_file_is_left_untouched(self):
        antigravity.hooks_path().parent.mkdir(parents=True)
        antigravity.hooks_path().write_text("{ not json", encoding="utf-8")
        with self.assertRaises(ConfigError):
            antigravity.install(COMMANDS)
        self.assertEqual(antigravity.hooks_path().read_text(), "{ not json")

    def test_doctor(self):
        antigravity.install(COMMANDS)
        self.assertTrue(all(c.ok for c in antigravity.doctor(COMMANDS)))
        self.assertFalse(antigravity.doctor(COMMANDS)[0].ok is False)
        other = system.Commands(Path("/elsewhere/perturbation.pyz")).for_agent("antigravity")
        self.assertFalse(antigravity.doctor(other)[1].ok)


class StatusLineSettingsTest(IsolatedTestCase):
    def test_owner_is_free_then_ours(self):
        self.assertIsNone(antigravity.statusline_owner())
        antigravity.install_statusline(STATUSLINE)
        self.assertEqual(antigravity.statusline_owner(), "ours")
        self.assertEqual(
            read_json(antigravity.settings_path())["statusLine"],
            {"type": "command", "command": STATUSLINE, "enabled": True, "stack_with_default": True},
        )

    def test_someone_elses_status_line_is_recognised(self):
        write_json(antigravity.settings_path(), {"statusLine": {"type": "command", "command": "~/my-own-line.sh"}})
        self.assertEqual(antigravity.statusline_owner(), "other")
        antigravity.uninstall_statusline()
        self.assertEqual(read_json(antigravity.settings_path())["statusLine"]["command"], "~/my-own-line.sh")

    def test_a_predecessors_status_line_is_ours_to_remove(self):
        write_json(antigravity.settings_path(), {"statusLine": {"type": "command", "command": "python3 '/x/antigravalgia.pyz' statusline"}})
        self.assertEqual(antigravity.statusline_owner(), "other")
        self.assertEqual(antigravity.statusline_owner(markers=("antigravalgia.pyz",)), "ours")
        antigravity.uninstall(("antigravalgia.pyz",))
        self.assertIsNone(antigravity.statusline_owner())

    def test_an_unreadable_settings_file_counts_as_taken(self):
        antigravity.settings_path().parent.mkdir(parents=True)
        antigravity.settings_path().write_text("{ not json", encoding="utf-8")
        self.assertEqual(antigravity.statusline_owner(), "other")

    def test_keeps_the_settings_the_cli_wrote_and_removes_only_ours(self):
        write_json(antigravity.settings_path(), FOREIGN_SETTINGS)
        antigravity.install_statusline(STATUSLINE)
        settings = read_json(antigravity.settings_path())
        self.assertEqual(settings["permissions"], FOREIGN_SETTINGS["permissions"])
        antigravity.uninstall_statusline()
        self.assertEqual(read_json(antigravity.settings_path()), FOREIGN_SETTINGS)


class AntigravityParseTest(IsolatedTestCase):
    # A real PreInvocation payload, captured from agy 1.2.7: no event name, no cwd, no session_id.
    PAYLOAD = {"conversationId": "054dbd28", "modelName": "gemini-3.8-flash-high", "workspacePaths": []}

    def test_busy_and_stop(self):
        self.assertEqual(antigravity.parse("busy", self.PAYLOAD).state, "busy")
        self.assertIsNone(antigravity.parse("stop", {**self.PAYLOAD, "fullyIdle": False}))
        done = antigravity.parse("stop", {**self.PAYLOAD, "fullyIdle": True})
        self.assertEqual((done.session_id, done.state, done.notice, done.project), ("054dbd28", "ready", ("ready", "Task finished"), None))
        self.assertIsNone(antigravity.parse(None, self.PAYLOAD))
        self.assertIsNone(antigravity.parse("SomethingNew", self.PAYLOAD))

    def test_project_comes_from_the_workspace(self):
        update = antigravity.parse("stop", {**self.PAYLOAD, "fullyIdle": True, "workspacePaths": ["/work/Đurđevac", "/other"]})
        self.assertEqual(update.project, "Đurđevac")
        self.assertEqual(antigravity.parse("busy", {}).session_id, "default")

    def test_statusline_payloads(self):
        base = {"conversation_id": "c1", "cwd": "/work/project", "workspace": {"current_dir": "/work/project"}}
        for agent_state in ("thinking", "working", "tool_use"):
            update, text = antigravity.statusline({**base, "agent_state": agent_state})
            self.assertEqual((update.state, text), ("busy", "working"))
        update, text = antigravity.statusline({**base, "agent_state": "idle"})
        self.assertEqual((update.state, update.notice, text), ("ready", ("ready", "Task finished"), "ready"))
        for agent_state in ("initializing", "something-new"):
            update, text = antigravity.statusline({**base, "agent_state": agent_state})
            self.assertEqual((update.state, update.notice, text), ("ready", None, "ready"))
        update, text = antigravity.statusline({**base, "agent_state": "tool_use", "tool_confirmation_pending": True})
        self.assertEqual((update.state, update.notice, update.project, text), ("waiting", ("needs_you", "Waiting for your confirmation"), "project", "needs you"))
