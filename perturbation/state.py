"""Per-agent, per-session state: hooks write one file per session, the host sums them up per agent.

Files live at <data>/sessions/<agent_id>/<session_id> and hold one word: busy, waiting or ready, with
the session's project name on a second line when a hook has learnt it (not every event carries it).
"""
import os
import sys
import threading
import time
from contextlib import contextmanager

from . import paths

BUSY = "busy"
WAITING = "waiting"  # blocked on you: a permission prompt or a question
READY = "ready"

# Damping. Not every agent signals an interrupt, a crash or a closed terminal, so a session busy with no
# activity for this long counts as ready, and one waiting for this long counts as ready too.
BUSY_STALE_SECONDS = int(os.environ.get("PERTURBATION_BUSY_STALE_SECONDS", 15 * 60))
WAITING_STALE_SECONDS = int(os.environ.get("PERTURBATION_WAITING_STALE_SECONDS", 60 * 60))
# Sessions that ended without an end event are forgotten after this long.
SESSION_STALE_SECONDS = 24 * 60 * 60


def _safe(name):
    return "".join(c for c in str(name) if c.isalnum() or c in "-_") or "default"


def path(agent_id, session_id):
    return paths.sessions_dir() / _safe(agent_id) / _safe(session_id)


def set_state(agent_id, session_id, value, project=None):
    target = path(agent_id, session_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    # A name of its own per writer, so two hooks writing at once can't rename each other's file.
    tmp = target.with_name(f"{target.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(value + (f"\n{project}" if project else ""), encoding="utf-8")
    os.replace(tmp, target)  # atomic, so the host never reads a half-written file


def _read(agent_id, session_id):
    target = path(agent_id, session_id)
    lines = target.read_text(encoding="utf-8").splitlines()
    return lines[0].strip() if lines else "", lines[1].strip() if len(lines) > 1 else None, target.stat().st_mtime_ns


def current(agent_id, session_id):
    """(state, mtime_ns) of a session, or None. The mtime tells whether it changed since."""
    try:
        value, _, stamp = _read(agent_id, session_id)
        return value, stamp
    except OSError:
        return None


def project(agent_id, session_id):
    """The project name a hook recorded for the session, or None."""
    try:
        return _read(agent_id, session_id)[1] or None
    except OSError:
        return None


def clear(agent_id, session_id):
    try:
        path(agent_id, session_id).unlink()
    except FileNotFoundError:
        pass


@contextmanager
def locked(agent_id):
    """Hold an exclusive lock for one agent while a hook reads, decides and writes.

    Some agents run two hooks at the same moment for one turn (opencode's two idle events, Antigravity's
    Stop hook and status line). Without the lock both read the same old state: one hides the other's
    notification, or both notify. The lock lives beside the sessions, never among them, and the OS
    releases it if a hook is killed.
    """
    path = paths.data_dir() / "locks" / f"{_safe(agent_id)}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+b") as handle:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)  # retries for about 10 s, then raises
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def sessions(agent_id, now=None):
    """[(session_id, effective state)] for one agent's live sessions, with the damping rules applied."""
    now = time.time() if now is None else now
    try:
        entries = list((paths.sessions_dir() / _safe(agent_id)).iterdir())
    except FileNotFoundError:
        return []
    live = []
    for entry in sorted(entries):
        if entry.name.endswith(".tmp"):
            continue
        try:
            age = now - entry.stat().st_mtime
            value = entry.read_text(encoding="utf-8").split("\n", 1)[0].strip()
        except OSError:
            continue
        if age > SESSION_STALE_SECONDS:
            continue
        if value == BUSY and age > BUSY_STALE_SECONDS:
            value = READY
        elif value == WAITING and age > WAITING_STALE_SECONDS:
            value = READY
        elif value not in (BUSY, WAITING):
            value = READY
        live.append((entry.name, value))
    return live


def summary(agent_id, now=None):
    """{"state": busy|waiting|ready, "busy": n, "waiting": n, "total": n} for one agent."""
    values = [value for _, value in sessions(agent_id, now)]
    busy = values.count(BUSY)
    waiting = values.count(WAITING)
    return {"state": BUSY if busy else WAITING if waiting else READY, "busy": busy, "waiting": waiting, "total": len(values)}


def overall(summaries, count_waiting_as_busy=False):
    """Combine per-agent summaries: busy if any agent is busy, else waiting if any waits, else ready."""
    busy = sum(s["busy"] for s in summaries)
    waiting = sum(s["waiting"] for s in summaries)
    if count_waiting_as_busy:
        busy, waiting = busy + waiting, 0
    return {"overall": BUSY if busy else WAITING if waiting else READY, "busy_sessions": busy, "waiting_sessions": waiting}
