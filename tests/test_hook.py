import json
import threading
import time
from unittest import mock

from perturbation import agents, config, hook, paths, state
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
    def test_an_ending_needs_work_before_it(self, send_):
        config.save({"notifications": True})
        claude("Stop")  # nothing was running, so there is nothing to announce
        claude("StopFailure", error_type="rate_limit")
        send_.assert_not_called()
        self.assertEqual(state.current("claude", "s1")[0], "ready")
        claude("Notification", notification_type="permission_prompt", message="Allow?")  # needs you is always news
        self.assertEqual(send_.call_count, 1)
        claude("Stop")  # waiting counts as work in progress
        self.assertEqual(send_.call_args.args[0], "Claude is ready · project")

    @mock.patch("perturbation.notify.send")
    def test_muted_agents_stay_quiet(self, send_):
        config.save({"notifications": True, "mute": {"claude": True}})
        claude("Stop")
        send_.assert_not_called()
        send("codex", {"hook_event_name": "UserPromptSubmit", "session_id": "s1"})
        send("codex", {"hook_event_name": "Stop", "session_id": "s1"})
        self.assertEqual(send_.call_args.args[0], "Codex is ready")

    @mock.patch("perturbation.notify.send")
    def test_sound_setting_and_non_ascii_project(self, send_):
        config.save({"notifications": True, "sound": False})
        claude("UserPromptSubmit", cwd="/work/Đurđevac")
        claude("Stop", cwd="/work/Đurđevac")
        self.assertEqual(send_.call_args.args[0], "Claude is ready · Đurđevac")
        self.assertFalse(send_.call_args.kwargs["sound"])

    @mock.patch("perturbation.notify.send", side_effect=OSError("no notifier"))
    def test_notifier_failure_does_not_lose_the_state(self, send_):
        config.save({"notifications": True})
        claude("Stop")
        self.assertEqual(state.summary("claude")["state"], "ready")

    @mock.patch("perturbation.notify.send")
    def test_the_project_name_survives_events_that_lack_it(self, send_):
        config.save({"notifications": True})
        send("goose", {"event": "PreToolUse", "session_id": "g1", "working_dir": "/work/Đurđevac"})
        send("goose", {"event": "Stop", "session_id": "g1", "last_assistant_message": "Done."})
        self.assertEqual(send_.call_args.args[:2], ("Goose is ready · Đurđevac", "Done."))
        self.assertEqual(state.project("goose", "g1"), "Đurđevac")

    def test_update_survives_the_json_round_trip(self):
        update = Update("s1", "waiting", Notice(NEEDS_YOU, "Wants to run: ls"), "project", 5.0)
        self.assertEqual(Update.from_json(json.loads(json.dumps(update.to_json()))), update)
        plain = Update("s1", None)
        self.assertEqual(Update.from_json(json.loads(json.dumps(plain.to_json()))), plain)


class SimultaneousHooksTest(IsolatedTestCase):
    """Some agents run two hooks for one ending at the same moment. They must take turns."""

    @mock.patch("perturbation.notify.send")
    def test_one_ending_reported_by_several_hooks_at_once_notifies_once(self, send_):
        config.save({"notifications": True})
        adapter = agents.get("opencode")
        hook.apply(adapter, Update("s1", state.BUSY))
        real_set_state = state.set_state

        def slow_set_state(*args, **kwargs):
            time.sleep(0.05)  # widen the gap between reading and writing, where the race lives
            return real_set_state(*args, **kwargs)

        ending = Update("s1", state.READY, Notice(READY, "Task finished"))
        with mock.patch("perturbation.state.set_state", side_effect=slow_set_state):
            threads = [threading.Thread(target=hook.apply, args=(adapter, ending)) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(send_.call_count, 1)
        self.assertEqual(state.current("opencode", "s1")[0], "ready")

    def test_the_lock_is_kept_out_of_the_sessions(self):
        hook.apply(agents.get("claude"), Update("s1", state.BUSY))
        self.assertEqual(state.summary("claude")["total"], 1)
        self.assertTrue((paths.data_dir() / "locks" / "claude.lock").exists())


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
