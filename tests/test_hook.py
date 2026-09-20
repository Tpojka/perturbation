import json
from unittest import mock

from perturbation import config, hook, paths, state
from perturbation.agents import codex
from perturbation.agents.base import NEEDS_YOU, READY, Notice, Update
from tests.support import IsolatedTestCase, stdin


def send(agent, payload, event=None):
    with mock.patch("sys.stdin", stdin(json.dumps(payload))):
        hook.main([agent, event] if event else [agent])


def claude(event, **fields):
    send("claude", {"hook_event_name": event, "session_id": "s1", "cwd": "/work/project", **fields})


class HookTest(IsolatedTestCase):
    def test_unknown_agent_bad_argv_and_garbage_are_ignored(self):
        send("nobody", {"hook_event_name": "Stop"})
        with mock.patch("sys.stdin", stdin("not json")):
            hook.main(["claude"])
            hook.main([])
        with mock.patch("sys.stdin", stdin("[1, 2]")):
            hook.main(["claude"])
        self.assertFalse(paths.sessions_dir().exists())

    def test_state_is_recorded_per_agent_and_session(self):
        claude("UserPromptSubmit")
        send("codex", {"hook_event_name": "UserPromptSubmit", "session_id": "s2"})
        self.assertEqual(state.current("claude", "s1")[0], "busy")
        self.assertEqual(state.current("codex", "s2")[0], "busy")
        claude("SessionEnd")
        self.assertIsNone(state.current("claude", "s1"))
        self.assertEqual(state.summary("codex")["total"], 1)

    @mock.patch("perturbation.notify.send")
    def test_no_notifications_unless_enabled(self, send_):
        claude("Stop")
        send_.assert_not_called()

    @mock.patch("perturbation.notify.send")
    def test_notifies_only_when_the_state_changes(self, send_):
        config.save({"notifications": True})
        claude("UserPromptSubmit")
        claude("Stop", last_assistant_message="**Done.** All tests pass.")
        self.assertEqual(send_.call_args.args[:2], ("Claude is ready · project", "Done. All tests pass."))
        self.assertEqual(send_.call_args.args[2], paths.icon("lamp-green"))
        claude("Stop")  # the same state again: no second notification
        self.assertEqual(send_.call_count, 1)
        claude("Notification", notification_type="permission_prompt", message="Bash command")
        self.assertEqual(send_.call_args.args[:3], ("Claude needs you · project", "Bash command", paths.icon("lamp-amber")))
        self.assertEqual(send_.call_count, 2)

    @mock.patch("perturbation.notify.send")
    def test_a_first_event_after_install_notifies(self, send_):
        config.save({"notifications": True})
        claude("Stop")  # no session file yet, still a transition into ready
        self.assertEqual(send_.call_count, 1)

    @mock.patch("perturbation.notify.send")
    def test_muted_agents_stay_quiet(self, send_):
        config.save({"notifications": True, "mute": {"claude": True}})
        claude("Stop")
        send_.assert_not_called()
        send("codex", {"hook_event_name": "Stop", "session_id": "s1"})
        self.assertEqual(send_.call_args.args[0], "Codex is ready")

    @mock.patch("perturbation.notify.send")
    def test_sound_setting_and_non_ascii_project(self, send_):
        config.save({"notifications": True, "sound": False})
        claude("Stop", cwd="/work/Đurđevac")
        self.assertEqual(send_.call_args.args[0], "Claude is ready · Đurđevac")
        self.assertFalse(send_.call_args.kwargs["sound"])

    @mock.patch("perturbation.notify.send", side_effect=OSError("no notifier"))
    def test_notifier_failure_does_not_lose_the_state(self, send_):
        config.save({"notifications": True})
        claude("Stop")
        self.assertEqual(state.summary("claude")["state"], "ready")

    def test_update_survives_the_json_round_trip(self):
        update = Update("s1", "waiting", Notice(NEEDS_YOU, "Wants to run: ls"), "project", 5.0)
        self.assertEqual(Update.from_json(json.loads(json.dumps(update.to_json()))), update)
        plain = Update("s1", None)
        self.assertEqual(Update.from_json(json.loads(json.dumps(plain.to_json()))), plain)


class DeferredUpdateTest(IsolatedTestCase):
    """Codex asks permission before deciding who answers, so "needs you" is applied after a grace period."""

    PERMISSION = {"hook_event_name": "PermissionRequest", "session_id": "s1", "cwd": "/work/project", "tool_name": "Bash", "tool_input": {"command": ["rm", "-rf", "build"]}}

    def request(self):
        with mock.patch("perturbation.hook.subprocess.Popen") as popen:
            send("codex", self.PERMISSION)
        (argv,) = popen.call_args.args
        return argv

    def test_the_hook_returns_at_once_and_starts_a_reminder(self):
        send("codex", {"hook_event_name": "UserPromptSubmit", "session_id": "s1"})
        stamp = state.current("codex", "s1")[1]
        argv = self.request()
        self.assertEqual(argv[1:5], [str(paths.app_file()), "remind", "codex", str(stamp)])
        update = Update.from_json(json.loads(argv[5]))
        self.assertEqual((update.state, update.delay, update.project), ("waiting", codex.APPROVAL_GRACE_SECONDS, "project"))
        self.assertEqual(update.notice, Notice(NEEDS_YOU, "Wants to run: rm -rf build"))
        self.assertEqual(state.current("codex", "s1")[0], "busy")  # nothing recorded yet

    @mock.patch("perturbation.notify.send")
    @mock.patch("perturbation.hook.time.sleep")
    def test_an_untouched_session_turns_amber_after_the_grace(self, sleep, send_):
        config.save({"notifications": True})
        send("codex", {"hook_event_name": "UserPromptSubmit", "session_id": "s1"})
        argv = self.request()
        hook.remind_main(argv[3:])
        sleep.assert_called_once_with(codex.APPROVAL_GRACE_SECONDS)
        self.assertEqual(state.current("codex", "s1")[0], "waiting")
        self.assertEqual(send_.call_args.args[:2], ("Codex needs you · project", "Wants to run: rm -rf build"))

    @mock.patch("perturbation.notify.send")
    @mock.patch("perturbation.hook.time.sleep")
    def test_a_session_that_moved_on_is_left_alone(self, sleep, send_):
        config.save({"notifications": True})
        send("codex", {"hook_event_name": "UserPromptSubmit", "session_id": "s1"})
        argv = self.request()
        # Codex approved the call itself and ran the tool: the state changed, so the reminder is dropped.
        state.set_state("codex", "s1", state.READY)
        hook.remind_main(argv[3:])
        self.assertEqual(state.current("codex", "s1")[0], "ready")
        send_.assert_not_called()

    @mock.patch("perturbation.hook.time.sleep")
    def test_reminder_garbage_is_harmless(self, sleep):
        hook.remind_main(["codex", "x", "{"])
        hook.remind_main([])
        self.assertEqual(state.summary("codex")["total"], 0)
