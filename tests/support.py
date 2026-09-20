"""Test isolation: every test gets its own home and data directory, so no real install is touched.

Agents keep their config under the home directory (some honour an env var, some don't), so the tests
move HOME itself, which is what Path.home() follows on every platform.
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]

# A "busy" payload for every agent, as its hook system sends it, and the argv the hook expects.
BUSY = {
    "claude": (None, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "cwd": "/work/project"}),
    "codex": (None, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "cwd": "/work/project"}),
    "copilot": (None, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "cwd": "/work/project"}),
    "antigravity": ("busy", {"conversationId": "s1", "workspacePaths": ["/work/project"]}),
    "opencode": (None, {"type": "session.status", "properties": {"sessionID": "s1", "status": {"type": "busy"}}}),
    "goose": (None, {"event": "UserPromptSubmit", "session_id": "s1"}),
    "qwen": (None, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "cwd": "/work/project"}),
}


def stdin(text):
    """A stand-in for sys.stdin that, like the real one, has a binary buffer."""
    return io.TextIOWrapper(io.BytesIO(text.encode("utf-8")), encoding="utf-8")


def shells(command, shell=None):
    """How agents run a hook command: as a string, through a shell. `shell` is "sh" for agents that use
    `sh -c` on every OS (on Windows that is Git Bash, when present)."""
    if sys.platform == "win32":
        if shell == "sh":
            sh = shutil.which("sh")
            return [[sh, "-c", command]] if sh else []
        return [["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command]]
    return [[s, "-c", command] for s in ("/bin/sh", shutil.which("bash")) if s]


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


AGENT_BINARIES = ("claude", "codex", "copilot", "agy", "opencode", "goose", "qwen")
_real_which = shutil.which


def _no_agents(name, *args, **kwargs):
    return None if name in AGENT_BINARIES else _real_which(name, *args, **kwargs)


class IsolatedTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = tmp.name
        # A space and a quote, like "Application Support" on macOS, so hook commands must quote the path.
        self.data = os.path.join(self.home, "data dir's")
        env = {
            "HOME": self.home,
            "USERPROFILE": self.home,
            "PERTURBATION_HOME": self.data,
            "XDG_CONFIG_HOME": os.path.join(self.home, ".config"),
            "XDG_DATA_HOME": os.path.join(self.home, ".local", "share"),
            "LOCALAPPDATA": os.path.join(self.home, "AppData", "Local"),
        }
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        for var in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "COPILOT_HOME", "CLAUDICATION_HOME", "CODEXALGIA_HOME", "COPILONIDAL_HOME", "ANTIGRAVALGIA_HOME"):
            os.environ.pop(var, None)
        os.makedirs(env["LOCALAPPDATA"], exist_ok=True)
        # Nothing on PATH looks like an agent unless a test says so (adapters import shutil themselves).
        which = mock.patch("shutil.which", side_effect=_no_agents)
        which.start()
        self.addCleanup(which.stop)
