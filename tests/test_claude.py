import os
from pathlib import Path
from unittest import mock

from perturbation.agents import claude
from perturbation.agents.base import ConfigError
from perturbation.install import system
from tests.support import IsolatedTestCase, read_json, write_json

COMMANDS = system.Commands(Path("/data/perturbation.pyz")).for_agent("claude")
COMMAND = COMMANDS.hook()
FOREIGN = {"type": "command", "command": "say done"}
LEGACY = {"type": "command", "command": 'python3 "/repo/hooks/claudication_hook.py" ready'}


class ClaudeSettingsTest(IsolatedTestCase):
    def commands(self, event):
        return [h["command"] for g in read_json(claude.settings_path())["hooks"].get(event, []) for h in g["hooks"]]

    def test_location_follows_claude_config_dir(self):
        self.assertEqual(claude.settings_path(), Path(self.home) / ".claude" / "settings.json")
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": os.path.join(self.home, "elsewhere")}):
            self.assertEqual(claude.settings_path(), Path(self.home) / "elsewhere" / "settings.json")

    def test_detect(self):
        self.assertIsNone(claude.detect())
        os.makedirs(claude.config_home())
        self.assertEqual(claude.detect(), "found ~/.claude")

    def test_registers_every_event_with_its_matcher(self):
        claude.install(COMMANDS)
        hooks = read_json(claude.settings_path())["hooks"]
        self.assertEqual(set(hooks), set(claude.EVENTS))
        for event, matcher in claude.EVENTS.items():
            (group,) = hooks[event]
            self.assertEqual(group.get("matcher"), matcher)
            self.assertEqual(group["hooks"], [{"type": "command", "command": COMMAND, "timeout": 5}])
        self.assertIn("permission_prompt|", hooks["Notification"][0]["matcher"])
        self.assertEqual(hooks["PreCompact"][0]["matcher"], "manual|auto")

    def test_keeps_other_settings_and_hooks_and_backs_up(self):
        write_json(claude.settings_path(), {"model": "opus", "hooks": {"Stop": [{"hooks": [FOREIGN]}]}})
        claude.install(COMMANDS)
        self.assertEqual(read_json(claude.settings_path())["model"], "opus")
        self.assertEqual(self.commands("Stop"), ["say done", COMMAND])
        backup = read_json(str(claude.settings_path()) + ".perturbation.bak")
        self.assertEqual(backup, {"model": "opus", "hooks": {"Stop": [{"hooks": [FOREIGN]}]}})

    def test_reinstall_does_not_duplicate(self):
        claude.install(COMMANDS)
        claude.install(COMMANDS)
        self.assertEqual(self.commands("Stop"), [COMMAND])
        self.assertEqual(claude.installed(), f"{len(claude.EVENTS)} hook entries in ~/.claude/settings.json")

    def test_uninstall_removes_only_ours_and_drops_the_empty_key(self):
        write_json(claude.settings_path(), {"model": "opus", "hooks": {"Stop": [{"hooks": [FOREIGN, LEGACY]}]}})
        claude.install(COMMANDS)
        claude.uninstall()
        self.assertEqual(read_json(claude.settings_path()), {"model": "opus", "hooks": {"Stop": [{"hooks": [FOREIGN, LEGACY]}]}})
        self.assertIsNone(claude.installed())
        claude.uninstall(("claudication_hook.py",))
        self.assertEqual(read_json(claude.settings_path()), {"model": "opus", "hooks": {"Stop": [{"hooks": [FOREIGN]}]}})
        claude.uninstall()  # nothing left of ours, nothing happens
        write_json(claude.settings_path(), {"hooks": {}})
        claude.install(COMMANDS)
        claude.uninstall()
        self.assertEqual(read_json(claude.settings_path()), {})

    def test_predecessor_entries_are_recognised(self):
        write_json(claude.settings_path(), {"hooks": {"Stop": [{"hooks": [LEGACY]}]}})
        self.assertIsNone(claude.installed())
        self.assertEqual(claude.installed(("claudication.pyz", "claudication_hook.py")), "1 hook entries in ~/.claude/settings.json")

    def test_an_unreadable_file_is_left_untouched(self):
        claude.settings_path().parent.mkdir(parents=True)
        claude.settings_path().write_text("{ not json", encoding="utf-8")
        with self.assertRaises(ConfigError):
            claude.install(COMMANDS)
        self.assertEqual(claude.settings_path().read_text(), "{ not json")
        self.assertIsNone(claude.installed())

    def test_doctor(self):
        claude.install(COMMANDS)
        self.assertTrue(all(c.ok for c in claude.doctor(COMMANDS)))
        other = system.Commands(Path("/elsewhere/perturbation.pyz")).for_agent("claude")
        self.assertFalse(claude.doctor(other)[1].ok)
        data = read_json(claude.settings_path())
        data["disableAllHooks"] = True
        write_json(claude.settings_path(), data)
        self.assertIn("disableAllHooks", claude.doctor(COMMANDS)[-1].text)


class ClaudeParseTest(IsolatedTestCase):
    def parse(self, event, **fields):
        return claude.parse(None, {"hook_event_name": event, "session_id": "abc", "cwd": "/work/project", **fields})

    def test_states(self):
        self.assertEqual(self.parse("SessionStart").state, "ready")
        for event in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "PreCompact"):
            self.assertEqual(self.parse(event).state, "busy", event)
        self.assertEqual(self.parse("SessionEnd").state, None)
        self.assertIsNone(self.parse("SubagentStop"))
        self.assertEqual(self.parse("Stop").session_id, "abc")
        self.assertEqual(self.parse("Stop").project, "project")

    def test_stop_notifies_with_the_last_message(self):
        update = self.parse("Stop", last_assistant_message="# Summary\n\nRefactored `state.py`.\nMore.")
        self.assertEqual(update.notice, ("ready", "Summary"))
        self.assertEqual(self.parse("Stop").notice, ("ready", "Task finished"))

    def test_notifications(self):
        needs = self.parse("Notification", notification_type="permission_prompt", message="Claude needs your permission to use Bash")
        self.assertEqual((needs.state, needs.notice), ("waiting", ("needs_you", "Claude needs your permission to use Bash")))
        self.assertEqual(self.parse("Notification", notification_type="elicitation_dialog").notice.message, "Claude is waiting for you")
        self.assertEqual(self.parse("Notification", notification_type="agent_needs_input").state, "waiting")
        idle = self.parse("Notification", notification_type="idle_prompt", message="Claude is waiting for your input")
        self.assertEqual((idle.state, idle.notice), ("ready", None))
        self.assertIsNone(self.parse("Notification", notification_type="auth_success"))
        # Older payloads carry no type: the idle reminder is known by its text, anything else is a prompt.
        self.assertEqual(self.parse("Notification", message="Claude is waiting for your input").state, "ready")
        self.assertEqual(self.parse("Notification", message="Needs permission").state, "waiting")

    def test_compaction_and_failure(self):
        manual = self.parse("PostCompact", trigger="manual")
        self.assertEqual((manual.state, manual.notice), ("ready", ("ready", "Context compacted")))
        auto = self.parse("PostCompact", trigger="auto")
        self.assertEqual((auto.state, auto.notice), ("busy", None))
        failed = self.parse("StopFailure", error_type="rate_limit", error_message="Too many requests")
        self.assertEqual((failed.state, failed.notice), ("ready", ("stopped", "rate_limit: Too many requests")))
        self.assertEqual(self.parse("StopFailure").notice.message, "error")

    def test_missing_ids_fall_back(self):
        update = claude.parse(None, {"hook_event_name": "Stop"})
        self.assertEqual((update.session_id, update.project), ("default", None))
