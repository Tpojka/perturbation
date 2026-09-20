"""The one hook handler for every agent: pick the adapter, parse the payload, record the session's
state, and notify when that state actually changed.

It prints nothing and always exits 0. Some agents deny a tool call, block a compaction or force a retry
when a hook fails or writes to stdout, so nothing here may ever reach the agent.
"""
import json
import os
import subprocess
import sys
import time

from . import agents, config, notify, paths, state
from .agents.base import NEEDS_YOU, READY, STOPPED, Notice, Update

TITLES = {READY: "{short} is ready", NEEDS_YOU: "{short} needs you", STOPPED: "{short} stopped"}
ICONS = {READY: "lamp-green", NEEDS_YOU: "lamp-amber", STOPPED: "lamp-red"}


def main(argv=None):
    """argv: [<agent id>, <event>] — the event only for agents whose payload doesn't name it."""
    try:
        argv = sys.argv[2:] if argv is None else argv
        adapter = agents.get(argv[0]) if argv else None
        if adapter is None:
            return
        event = argv[1] if len(argv) > 1 else None
        # Bytes, because the payload is UTF-8 and Windows would decode text stdin with the ANSI code page.
        payload = json.loads(sys.stdin.buffer.read())
        if not isinstance(payload, dict):
            return
        update = adapter.parse(event, payload)
        if update is None:
            return
        if update.delay > 0:
            defer(adapter, update)
        else:
            apply(adapter, update)
    except Exception:
        pass  # a failing hook must never disturb the agent


def apply(adapter, update):
    """Record the update and notify only when the session's stored state actually changed."""
    previous = state.current(adapter.ID, update.session_id)
    if update.state is None:
        state.clear(adapter.ID, update.session_id)
        return
    # Not every event names the project (Goose's Stop, opencode's idle), so the last one seen is kept.
    project = update.project or state.project(adapter.ID, update.session_id)
    state.set_state(adapter.ID, update.session_id, update.state, project)
    if update.notice and (previous is None or previous[0] != update.state):
        _notify(adapter, update._replace(project=project))


def _notify(adapter, update):
    settings = config.load()
    if not settings["notifications"] or settings["mute"].get(adapter.ID):
        return
    title = TITLES[update.notice.kind].format(short=adapter.SHORT)
    if update.project:
        title += f" · {update.project}"
    try:
        notify.send(title, update.notice.message, paths.icon(ICONS[update.notice.kind]), sound=settings["sound"])
    except Exception:
        pass  # a notifier that can't run is no reason to lose the state change


def defer(adapter, update):
    """Apply `update` after `update.delay` seconds, unless the session changes meanwhile.

    The hook returns at once and a detached `remind` process waits, so an agent that answers its own
    permission prompt within the delay never turns the lamp amber.
    """
    current = state.current(adapter.ID, update.session_id)
    stamp = current[1] if current else 0
    command = [sys.executable, str(paths.app_file()), "remind", adapter.ID, str(stamp), json.dumps(update.to_json())]
    quiet = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        subprocess.Popen(command, creationflags=notify.CREATE_NO_WINDOW, **quiet)
    else:
        subprocess.Popen(command, start_new_session=True, **quiet)


def remind_main(argv):
    """argv: [<agent id>, <mtime stamp>, <update as JSON>]. Runs detached, with nobody to report to."""
    try:
        adapter = agents.get(argv[0])
        update = Update.from_json(json.loads(argv[2]))
        remind(adapter, int(argv[1]), update)
    except Exception:
        pass


def remind(adapter, stamp, update):
    time.sleep(update.delay)
    current = state.current(adapter.ID, update.session_id)
    if (current[1] if current else 0) == stamp:
        apply(adapter, update._replace(delay=0))


def project_of(*candidates):
    """The project name for a notification title: the last path component of the first usable candidate."""
    for candidate in candidates:
        if candidate:
            return os.path.basename(os.path.normpath(str(candidate))) or None
    return None
