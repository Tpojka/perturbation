import os
import sys
from pathlib import Path

from perturbation.agents import qwen
from perturbation.agents.base import ConfigError
from perturbation.install import system
from tests.support import IsolatedTestCase, read_json, write_json

COMMANDS = system.Commands(Path("/data/perturbation.pyz")).for_agent("qwen")
COMMAND = COMMANDS.hook()
FOREIGN = {"type": "command", "command": "say done"}


class QwenSettingsTest(IsolatedTestCase):
    def commands(self, event):
        return [h["command"] for g in read_json(qwen.settings_path())["hooks"].get(event, []) for h in g["hooks"]]

    def test_location_and_detect(self):
        self.assertEqual(qwen.settings_path(), Path(self.home) / ".qwen" / "settings.json")
        self.assertIsNone(qwen.detect())
        os.makedirs(qwen.config_home())
        self.assertEqual(qwen.detect(), "found ~/.qwen")

    def test_registers_every_event_with_its_matcher_and_shell(self):
        qwen.install(COMMANDS)
        hooks = read_json(qwen.settings_path())["hooks"]
        self.assertEqual(set(hooks), set(qwen.EVENTS))
        for event, matcher in qwen.EVENTS.items():
            (group,) = hooks[event]
            self.assertEqual(group.get("matcher"), matcher)
            (entry,) = group["hooks"]
            self.assertEqual((entry["type"], entry["command"], entry["name"], entry["timeout"]), ("command", COMMAND, "perturbation", 5))
            # Qwen picks the shell per hook: PowerShell on Windows, its bash default elsewhere.
            self.assertEqual(entry.get("shell"), "powershell" if sys.platform == "win32" else None)
        self.assertEqual(qwen.installed(), f"{len(qwen.EVENTS)} hook entries in ~/.qwen/settings.json")

    def test_keeps_other_settings_and_hooks(self):
        write_json(qwen.settings_path(), {"theme": "dark", "hooks": {"Stop": [{"hooks": [FOREIGN]}]}})
        qwen.install(COMMANDS)
        qwen.install(COMMANDS)
        self.assertEqual(read_json(qwen.settings_path())["theme"], "dark")
        self.assertEqual(self.commands("Stop"), ["say done", COMMAND])
        qwen.uninstall()
        self.assertEqual(read_json(qwen.settings_path()), {"theme": "dark", "hooks": {"Stop": [{"hooks": [FOREIGN]}]}})
        self.assertIsNone(qwen.installed())

    def test_an_unreadable_file_is_left_untouched(self):
        qwen.settings_path().parent.mkdir(parents=True)
        qwen.settings_path().write_text("{ not json", encoding="utf-8")
        with self.assertRaises(ConfigError):
            qwen.install(COMMANDS)
        self.assertEqual(qwen.settings_path().read_text(), "{ not json")

    def test_doctor(self):
        qwen.install(COMMANDS)
        self.assertTrue(all(c.ok for c in qwen.doctor(COMMANDS)))
        data = read_json(qwen.settings_path())
        data["disableAllHooks"] = True
        write_json(qwen.settings_path(), data)
        self.assertIn("disableAllHooks", qwen.doctor(COMMANDS)[-1].text)


class QwenParseTest(IsolatedTestCase):
    def parse(self, event, **fields):
        return qwen.parse(None, {"hook_event_name": event, "session_id": "abc", "cwd": "/work/project", **fields})

    def test_states(self):
        self.assertEqual(self.parse("SessionStart").state, "ready")
        for event in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure", "PreCompact"):
            self.assertEqual(self.parse(event).state, "busy", event)
        self.assertEqual(self.parse("SessionEnd").state, None)
        self.assertIsNone(self.parse("TodoCreated"))
        self.assertEqual(self.parse("Stop", last_assistant_message="**Done**").notice, ("ready", "Done"))
        self.assertEqual(self.parse("Stop").project, "project")

    def test_needs_you(self):
        prompt = self.parse("Notification", notification_type="permission_prompt", message="Allow write_file?")
        self.assertEqual((prompt.state, prompt.notice), ("waiting", ("needs_you", "Allow write_file?")))
        self.assertEqual(self.parse("Notification", notification_type="idle_prompt").state, "ready")
        self.assertIsNone(self.parse("Notification", notification_type="auth_success"))
        request = self.parse("PermissionRequest", tool_name="run_shell_command", tool_input={"command": "git push"})
        self.assertEqual((request.state, request.notice, request.delay), ("waiting", ("needs_you", "Wants to run: git push"), 0))
        self.assertEqual(self.parse("PermissionRequest", tool_name="write_file").notice.message, "Wants to use write_file")

    def test_failures_and_compaction(self):
        failed = self.parse("StopFailure", error="rate_limit", error_details="429")
        self.assertEqual((failed.state, failed.notice), ("ready", ("stopped", "rate_limit: 429")))
        self.assertEqual(self.parse("StopFailure", error="loop_detected").notice.message, "loop_detected")
        self.assertEqual(self.parse("PostCompact", trigger="manual").notice, ("ready", "Context compacted"))
        self.assertEqual(self.parse("PostCompact", trigger="auto").state, "busy")
