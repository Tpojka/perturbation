import io
import json
from unittest import mock

from perturbation import config, hook, state, statusline
from tests.support import IsolatedTestCase, stdin

# The shape of the payload Antigravity pipes to a status line script, trimmed to the fields we read.
PAYLOAD = {
    "cwd": "/work/project",
    "conversation_id": "054dbd28",
    "session_id": "054dbd28",
    "workspace": {"current_dir": "/work/project", "project_dir": "/work/project"},
    "agent_state": "idle",
    "tool_confirmation_pending": False,
}


class StatusLineTest(IsolatedTestCase):
    def run_with(self, payload, argv=("antigravity",)):
        """Return the raw bytes the status line wrote to stdout."""
        out = io.BytesIO()
        with mock.patch("sys.stdin", stdin(payload.decode("utf-8", "replace"))):
            with mock.patch("sys.stdout", mock.Mock(buffer=out)):
                statusline.main(list(argv))
        return out.getvalue()

    def send(self, **payload):
        written = self.run_with(json.dumps({**PAYLOAD, **payload}).encode("utf-8"))
        self.assertEqual(written.count(b"\n"), 1, f"expected one line, got {written!r}")
        self.assertNotIn(b"\r", written)
        return written[:-1].decode("utf-8")

    def test_records_the_state_and_names_it(self):
        self.assertEqual(self.send(agent_state="working"), "perturbation · working")
        self.assertEqual(state.summary("antigravity")["state"], "busy")
        self.assertEqual(self.send(tool_confirmation_pending=True), "perturbation · needs you")
        self.assertEqual(state.summary("antigravity")["state"], "waiting")
        state.set_state("antigravity", "another", state.BUSY)
        self.assertEqual(self.send(agent_state="idle"), "perturbation · ready · 1 of 2 sessions working")

    def test_the_line_is_utf8_bytes(self):
        self.assertEqual(self.run_with(json.dumps(PAYLOAD).encode()), "perturbation · ready\n".encode("utf-8"))

    def test_garbage_unknown_agent_and_agents_without_a_status_line_write_one_empty_line(self):
        self.assertEqual(self.run_with(b"not json"), b"\n")
        self.assertEqual(self.run_with(b"[]"), b"\n")
        self.assertEqual(self.run_with(json.dumps(PAYLOAD).encode(), argv=("nobody",)), b"\n")
        self.assertEqual(self.run_with(json.dumps(PAYLOAD).encode(), argv=("claude",)), b"\n")
        self.assertEqual(self.run_with(json.dumps(PAYLOAD).encode(), argv=()), b"\n")
        self.assertEqual(state.summary("antigravity")["total"], 0)

    @mock.patch("perturbation.notify.send")
    def test_needs_you_notifies_once_per_dialog(self, send):
        config.save({"notifications": True})
        self.send(agent_state="tool_use", tool_confirmation_pending=True)
        self.assertEqual(send.call_args.args[:2], ("Antigravity needs you · project", "Waiting for your confirmation"))
        self.send(agent_state="working", tool_confirmation_pending=True)  # the same dialog, redrawn
        self.assertEqual(send.call_count, 1)
        self.send(agent_state="tool_use")
        self.send(agent_state="tool_use", tool_confirmation_pending=True)  # a new dialog
        self.assertEqual(send.call_count, 2)

    @mock.patch("perturbation.notify.send")
    def test_the_end_of_a_turn_notifies_once_whether_the_status_line_or_the_stop_hook_is_first(self, send):
        config.save({"notifications": True})
        self.send(agent_state="idle")  # a fresh session starts idle: nothing has run, nothing to announce
        send.assert_not_called()
        self.send(agent_state="working")
        self.send(agent_state="idle")
        self.assertEqual(send.call_args.args[:2], ("Antigravity is ready · project", "Task finished"))
        with mock.patch("sys.stdin", stdin(json.dumps({"conversationId": PAYLOAD["conversation_id"], "fullyIdle": True}))):
            hook.main(["antigravity", "stop"])  # the Stop hook reports the same ending
        self.assertEqual(send.call_count, 1)

    @mock.patch("perturbation.notify.send", side_effect=OSError("no notifier"))
    def test_a_failing_notifier_still_prints_the_line(self, send):
        config.save({"notifications": True})
        self.assertEqual(self.send(workspace=None, cwd="/work/Đurđevac", tool_confirmation_pending=True), "perturbation · needs you")
        self.assertEqual(state.current("antigravity", "054dbd28")[0], state.WAITING)
