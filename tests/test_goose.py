import json
import os
from pathlib import Path

from perturbation.agents import goose
from perturbation.install import system
from tests.support import IsolatedTestCase, read_json, write_json

COMMANDS = system.Commands(Path("/data/perturbation.pyz")).for_agent("goose")


class GoosePluginTest(IsolatedTestCase):
    def test_locations_and_detect(self):
        self.assertEqual(goose.hooks_path(), Path(self.home) / ".agents" / "plugins" / "perturbation" / "hooks" / "hooks.json")
        self.assertEqual(goose.settings_path(), Path(self.home) / ".config" / "goose" / "settings.json")
        self.assertIsNone(goose.detect())
        os.makedirs(goose.config_home())
        self.assertEqual(goose.detect(), "found ~/.config/goose")

    def test_writes_a_plugin_with_a_posix_command_for_every_event(self):
        goose.install(COMMANDS)
        self.assertEqual(read_json(goose.manifest_path())["name"], "perturbation")
        hooks = read_json(goose.hooks_path())["hooks"]
        self.assertEqual(set(hooks), set(goose.EVENTS))
        for event, (group,) in hooks.items():
            self.assertNotIn("matcher", group)
            (entry,) = group["hooks"]
            self.assertEqual(entry["type"], "command")
            self.assertEqual(entry["timeout"], 5)
            # Goose runs hooks with `sh -c` everywhere, so no PowerShell, whatever the OS.
            self.assertTrue(entry["command"].endswith("hook goose || true"), entry["command"])
            self.assertNotIn("exit 0", entry["command"])
        self.assertEqual(goose.installed(), "~/.agents/plugins/perturbation")

    def test_uninstall_removes_only_our_plugin(self):
        other = goose.plugins_dir() / "hello-hooks" / "hooks" / "hooks.json"
        write_json(other, {"hooks": {}})
        goose.install(COMMANDS)
        goose.uninstall()
        goose.uninstall()
        self.assertEqual(os.listdir(goose.plugins_dir()), ["hello-hooks"])
        self.assertIsNone(goose.installed())

    def test_disabled_plugins_are_noticed(self):
        goose.install(COMMANDS)
        self.assertTrue(all(c.ok for c in goose.doctor(COMMANDS)))
        write_json(goose.settings_path(), {"disabledPlugins": ["perturbation"]})
        self.assertTrue(goose.disabled())
        self.assertIn("disabledPlugins", next(c.text for c in goose.doctor(COMMANDS) if not c.ok))
        goose.settings_path().write_text("{ not json")
        self.assertFalse(goose.disabled())


class GooseParseTest(IsolatedTestCase):
    def parse(self, event, **fields):
        return goose.parse(None, {"event": event, "session_id": "abc", **fields})

    def test_states(self):
        self.assertEqual(self.parse("SessionStart").state, "ready")
        for event in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure", "BeforeShellExecution", "AfterShellExecution", "BeforeReadFile", "AfterFileEdit"):
            self.assertEqual(self.parse(event).state, "busy", event)
        self.assertEqual(self.parse("SessionEnd").state, None)
        self.assertIsNone(self.parse("PreToolUseResult"))
        self.assertIsNone(goose.parse(None, {"hook_event_name": "Stop"}))

    def test_project_and_stop_message(self):
        busy = self.parse("PreToolUse", working_dir="/work/Đurđevac", tool_name="developer__shell")
        self.assertEqual((busy.session_id, busy.project), ("abc", "Đurđevac"))
        done = self.parse("Stop", last_assistant_message="Done. I updated the file and ran the tests.")
        self.assertEqual((done.state, done.notice, done.project), ("ready", ("ready", "Done. I updated the file and ran the tests."), None))
        self.assertEqual(self.parse("Stop").notice.message, "Task finished")
