import io
import json
import os
import struct
import subprocess
import sys
import time

from perturbation import __version__, agents, config, host, state
from tests.support import REPO, IsolatedTestCase


def read_message(stream):
    (length,) = struct.unpack("@I", stream.read(4))
    return json.loads(stream.read(length))


class StatusTest(IsolatedTestCase):
    def test_message_shape_and_order(self):
        config.save({"agents": ["claude", "codex"], "order": ["codex", "claude"], "mute": {"codex": True}})
        state.set_state("claude", "a", state.BUSY)
        state.set_state("claude", "b", state.READY)
        state.set_state("codex", "a", state.WAITING)
        state.set_state("copilot", "a", state.BUSY)  # not watched, so not counted
        message = host.status()
        self.assertEqual(message["type"], "status")
        self.assertEqual(message["version"], __version__)
        self.assertEqual((message["overall"], message["busy_sessions"], message["waiting_sessions"]), ("busy", 1, 1))
        self.assertEqual([a["id"] for a in message["agents"]], ["codex", "claude"] + [i for i in agents.ids() if i not in ("codex", "claude")])
        codex, claude = message["agents"][:2]
        self.assertEqual(codex, {"id": "codex", "name": "Codex CLI", "short": "Codex", "watched": True, "muted": True, "state": "waiting", "busy": 0, "waiting": 1, "total": 1})
        self.assertEqual((claude["state"], claude["busy"], claude["total"], claude["muted"]), ("busy", 1, 2, False))
        copilot = next(a for a in message["agents"] if a["id"] == "copilot")
        self.assertEqual((copilot["watched"], copilot["total"], copilot["state"]), (False, 0, "ready"))

    def test_nothing_watched(self):
        message = host.status()
        self.assertEqual((message["overall"], message["busy_sessions"]), ("ready", 0))
        self.assertFalse(any(a["watched"] for a in message["agents"]))

    def test_waiting_as_busy(self):
        config.save({"agents": ["claude"], "count_waiting_as_busy": True})
        state.set_state("claude", "a", state.WAITING)
        message = host.status()
        self.assertEqual((message["overall"], message["busy_sessions"], message["waiting_sessions"]), ("busy", 1, 0))

    def test_settings_messages_from_the_popup(self):
        config.save({"agents": ["claude"]})
        self.assertTrue(host.handle({"type": "mute", "id": "codex", "muted": True}, config.load()))
        self.assertEqual(config.load()["mute"], {"codex": True})
        self.assertTrue(host.handle({"type": "mute", "id": "codex", "muted": False}, config.load()))
        self.assertEqual(config.load()["mute"], {})
        self.assertTrue(host.handle({"type": "order", "ids": ["copilot", "nobody", 3, "claude"]}, config.load()))
        self.assertEqual(config.load()["order"], ["copilot", "claude"])
        self.assertTrue(host.handle({"type": "get"}, config.load()))
        self.assertFalse(host.handle({"type": "nonsense"}, config.load()))
        self.assertFalse(host.handle("garbage", config.load()))
        self.assertEqual(config.load()["agents"], ["claude"])

    def test_frames(self):
        frame = host.encode({"type": "status"})
        (length,) = struct.unpack("@I", frame[:4])
        self.assertEqual(length, len(frame) - 4)
        self.assertEqual(host.read_message(io.BytesIO(frame)), {"type": "status"})
        self.assertIsNone(host.read_message(io.BytesIO(frame[:3])))
        self.assertEqual(host.read_message(io.BytesIO(struct.pack("@I", 3) + b"{x}")), {})


class HostProcessTest(IsolatedTestCase):
    def test_pushes_status_on_change_takes_settings_and_exits_when_stdin_closes(self):
        config.save({"agents": ["claude"]})
        proc = subprocess.Popen([sys.executable, "-m", "perturbation", "host"], cwd=str(REPO), stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        try:
            first = read_message(proc.stdout)
            self.assertEqual((first["type"], first["overall"]), ("status", "ready"))
            state.set_state("claude", "s1", state.BUSY)
            second = read_message(proc.stdout)
            self.assertEqual((second["overall"], second["busy_sessions"]), ("busy", 1))
            proc.stdin.write(host.encode({"type": "mute", "id": "claude", "muted": True}))
            proc.stdin.flush()
            third = read_message(proc.stdout)
            self.assertTrue(third["agents"][0]["muted"])
            for _ in range(50):
                if config.load()["mute"] == {"claude": True}:
                    break
                time.sleep(0.1)
            self.assertEqual(config.load()["mute"], {"claude": True})
            proc.stdin.close()
            self.assertEqual(proc.wait(timeout=10), 0)
        finally:
            proc.kill()
            proc.stdout.close()
