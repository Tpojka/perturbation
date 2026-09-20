import os
import time

from perturbation import paths, state
from tests.support import IsolatedTestCase

EMPTY = {"state": "ready", "busy": 0, "waiting": 0, "total": 0}


class StateTest(IsolatedTestCase):
    def test_no_sessions_is_ready(self):
        self.assertEqual(state.summary("claude"), EMPTY)

    def test_sessions_are_kept_per_agent(self):
        state.set_state("claude", "a", state.BUSY)
        state.set_state("codex", "a", state.READY)
        self.assertEqual(state.summary("claude"), {"state": "busy", "busy": 1, "waiting": 0, "total": 1})
        self.assertEqual(state.summary("codex"), {"state": "ready", "busy": 0, "waiting": 0, "total": 1})
        self.assertEqual(state.summary("copilot"), EMPTY)

    def test_any_busy_session_makes_the_agent_busy(self):
        state.set_state("claude", "a", state.BUSY)
        state.set_state("claude", "b", state.WAITING)
        state.set_state("claude", "c", state.READY)
        self.assertEqual(state.summary("claude"), {"state": "busy", "busy": 1, "waiting": 1, "total": 3})

    def test_waiting_outranks_ready_but_not_busy(self):
        state.set_state("claude", "a", state.WAITING)
        state.set_state("claude", "b", state.READY)
        self.assertEqual(state.summary("claude")["state"], "waiting")

    def test_current_reads_back_what_was_written(self):
        self.assertIsNone(state.current("claude", "a"))
        state.set_state("claude", "a", state.WAITING)
        value, stamp = state.current("claude", "a")
        self.assertEqual(value, state.WAITING)
        self.assertIsInstance(stamp, int)

    def test_the_project_name_is_kept_beside_the_state(self):
        state.set_state("claude", "a", state.BUSY, "project")
        self.assertEqual(state.current("claude", "a")[0], "busy")
        self.assertEqual(state.project("claude", "a"), "project")
        self.assertEqual(state.summary("claude"), {"state": "busy", "busy": 1, "waiting": 0, "total": 1})
        state.set_state("claude", "a", state.READY)
        self.assertIsNone(state.project("claude", "a"))
        self.assertIsNone(state.project("claude", "never"))

    def test_clear_removes_session(self):
        state.set_state("claude", "a", state.BUSY)
        state.clear("claude", "a")
        state.clear("claude", "never-existed")
        state.clear("nobody", "a")
        self.assertEqual(state.summary("claude")["total"], 0)

    def test_stale_busy_session_counts_as_ready(self):
        state.set_state("claude", "a", state.BUSY)
        later = time.time() + state.BUSY_STALE_SECONDS + 1
        self.assertEqual(state.summary("claude", now=later), {"state": "ready", "busy": 0, "waiting": 0, "total": 1})

    def test_stale_waiting_session_counts_as_ready(self):
        state.set_state("claude", "a", state.WAITING)
        self.assertEqual(state.summary("claude", now=time.time() + state.BUSY_STALE_SECONDS + 1)["state"], "waiting")
        later = time.time() + state.WAITING_STALE_SECONDS + 1
        self.assertEqual(state.summary("claude", now=later)["state"], "ready")

    def test_abandoned_session_is_ignored(self):
        state.set_state("claude", "a", state.READY)
        later = time.time() + state.SESSION_STALE_SECONDS + 1
        self.assertEqual(state.summary("claude", now=later)["total"], 0)

    def test_ids_cannot_escape_the_sessions_dir(self):
        state.set_state("../evil", "../../evil", state.BUSY)
        self.assertEqual(os.listdir(paths.sessions_dir()), ["evil"])
        self.assertEqual(os.listdir(paths.sessions_dir() / "evil"), ["evil"])

    def test_unknown_words_and_partial_writes(self):
        state.set_state("claude", "a", "something-new")
        (paths.sessions_dir() / "claude" / "b.tmp").write_text("busy")
        self.assertEqual(state.summary("claude"), {"state": "ready", "busy": 0, "waiting": 0, "total": 1})

    def test_overall_across_agents(self):
        summaries = [
            {"state": "busy", "busy": 2, "waiting": 0, "total": 3},
            {"state": "waiting", "busy": 0, "waiting": 1, "total": 1},
            {"state": "ready", "busy": 0, "waiting": 0, "total": 0},
        ]
        self.assertEqual(state.overall(summaries), {"overall": "busy", "busy_sessions": 2, "waiting_sessions": 1})
        self.assertEqual(state.overall(summaries[1:]), {"overall": "waiting", "busy_sessions": 0, "waiting_sessions": 1})
        self.assertEqual(state.overall(summaries[2:]), {"overall": "ready", "busy_sessions": 0, "waiting_sessions": 0})
        self.assertEqual(state.overall([]), {"overall": "ready", "busy_sessions": 0, "waiting_sessions": 0})

    def test_waiting_can_count_as_busy(self):
        summaries = [{"state": "waiting", "busy": 1, "waiting": 2, "total": 3}]
        self.assertEqual(state.overall(summaries, count_waiting_as_busy=True), {"overall": "busy", "busy_sessions": 3, "waiting_sessions": 0})
