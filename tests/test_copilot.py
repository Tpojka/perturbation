import os
from pathlib import Path

from perturbation.agents import copilot
from perturbation.install import system
from tests.support import IsolatedTestCase, read_json, write_json

COMMANDS = system.Commands(Path("/data/perturbation.pyz")).for_agent("copilot")


class CopilotHooksTest(IsolatedTestCase):
    def test_location_follows_copilot_home(self):
        self.assertEqual(copilot.hooks_path(), Path(self.home) / ".copilot" / "hooks" / "perturbation.json")
        os.environ["COPILOT_HOME"] = os.path.join(self.home, "elsewhere")
        self.assertEqual(copilot.hooks_path(), Path(self.home) / "elsewhere" / "hooks" / "perturbation.json")
        self.assertEqual(copilot.hooks_path("copilonidal.pyz"), Path(self.home) / "elsewhere" / "hooks" / "copilonidal.json")

    def test_registers_every_event_in_our_own_file(self):
        copilot.install(COMMANDS)
        data = read_json(copilot.hooks_path())
        self.assertEqual(data["version"], 1)
        self.assertEqual(set(data["hooks"]), set(copilot.EVENTS))
        # PascalCase names get the payload the hook reads; notification has no PascalCase name.
        self.assertEqual([e for e in data["hooks"] if e[0].islower()], ["notification"])
        for event, (entry,) in data["hooks"].items():
            self.assertEqual(entry["type"], "command")
            self.assertEqual(entry[COMMANDS.shell], COMMANDS.hook())
            self.assertEqual(entry["timeoutSec"], 5)
            self.assertEqual("matcher" in entry, event == "notification")
        self.assertEqual(data["hooks"]["notification"][0]["matcher"], "permission_prompt|elicitation_dialog")
        self.assertEqual(copilot.installed(), "~/.copilot/hooks/perturbation.json")

    def test_reinstall_replaces_the_file_and_uninstall_leaves_other_files(self):
        other = copilot.hooks_path().parent / "mine.json"
        write_json(other, {"version": 1, "hooks": {}})
        write_json(copilot.hooks_path("copilonidal.pyz"), {"version": 1, "hooks": {}})
        copilot.install(COMMANDS)
        copilot.install(COMMANDS)
        self.assertEqual(sorted(os.listdir(other.parent)), ["copilonidal.json", "mine.json", "perturbation.json"])
        self.assertEqual(copilot.installed(("copilonidal.pyz",)), "~/.copilot/hooks/copilonidal.json")
        copilot.uninstall()
        copilot.uninstall()
        copilot.uninstall(("copilonidal.pyz",))
        self.assertEqual(os.listdir(other.parent), ["mine.json"])
        self.assertIsNone(copilot.installed())

    def test_doctor(self):
        self.assertFalse(copilot.doctor(COMMANDS)[0].ok)
        copilot.install(COMMANDS)
        self.assertTrue(all(c.ok for c in copilot.doctor(COMMANDS)))
        other = system.Commands(Path("/elsewhere/perturbation.pyz")).for_agent("copilot")
        self.assertFalse(copilot.doctor(other)[1].ok)


class CopilotParseTest(IsolatedTestCase):
    def parse(self, event, **fields):
        return copilot.parse(None, {"hook_event_name": event, "session_id": "abc", "cwd": "/work/project", **fields})

    def test_states(self):
        self.assertEqual(self.parse("SessionStart").state, "ready")
        for event in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure"):
            self.assertEqual(self.parse(event).state, "busy", event)
        self.assertEqual(self.parse("Stop").notice, ("ready", "Task finished"))
        self.assertEqual(self.parse("SessionEnd").state, None)
        self.assertIsNone(self.parse("SubagentStop"))

    def test_notifications_only_when_copilot_waits_for_you(self):
        needs = self.parse("Notification", notification_type="permission_prompt", message="Allow ls?")
        self.assertEqual((needs.state, needs.notice), ("waiting", ("needs_you", "Allow ls?")))
        self.assertEqual(self.parse("Notification", notification_type="elicitation_dialog").notice.message, "Copilot is waiting for you")
        self.assertIsNone(self.parse("Notification", notification_type="background_shell"))

    def test_the_notification_payload_uses_a_camel_case_session_id(self):
        update = copilot.parse(None, {"hook_event_name": "Notification", "sessionId": "xyz", "notification_type": "permission_prompt"})
        self.assertEqual(update.session_id, "xyz")

    def test_unrecoverable_errors_end_the_turn(self):
        self.assertEqual(self.parse("ErrorOccurred", recoverable=False).state, "ready")
        self.assertIsNone(self.parse("ErrorOccurred", recoverable=True))
        self.assertIsNone(self.parse("ErrorOccurred"))
