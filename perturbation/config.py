"""User choices made at install time, read by the hook on every event and by the host on every poll.

Every reader here is on a hot path - one hook process per agent event, one host process per browser
polling twice a second - while the writers are the installer and the popup. So the file is replaced in
one step rather than rewritten in place: a reader sees the file it had or the new one, never half of
either. A half-read used to fall back to the defaults, and a popup that then saved wrote those defaults
back over every setting.
"""
import copy
import json
import os
import threading

from . import paths

DEFAULTS = {
    "notifications": False,
    "sound": True,
    "agents": [],  # ids of the agents being watched (their hooks are installed)
    "browsers": [],  # ids of the browsers the native host is registered with
    "order": [],  # popup and tooltip order; ids missing here follow in the registry's order
    "mute": {},  # {agent_id: true} silences that agent's notifications
    "statusline": {},  # {agent_id: true} when we own that agent's status line
    "count_waiting_as_busy": False,  # fold "needs you" into the red lamp
}


def load():
    try:
        data = json.loads(paths.config_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    settings = {}
    for key, default in DEFAULTS.items():
        value = data.get(key)
        # Copies, never the defaults themselves: callers edit what they get back.
        settings[key] = copy.deepcopy(value if isinstance(value, type(default)) else default)
    return settings


def save(settings):
    """Replace config.json atomically. The temporary name carries the process and thread, so two
    writers at once never share it."""
    path = paths.config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def damaged():
    """True when config.json is there but can't be read as settings.

    load() answers with the defaults in that case, so readers keep working; anything that would write
    the file back asks this first, because saving defaults over a file we failed to read loses the lot.
    """
    try:
        text = paths.config_file().read_text(encoding="utf-8")
    except OSError:
        return False  # missing is not damaged: that is a machine with nothing installed yet
    try:
        return not isinstance(json.loads(text), dict)
    except ValueError:
        return True


def mtime():
    """When config.json last changed, or 0 when it doesn't exist. Lets the host reload it only on change."""
    try:
        return paths.config_file().stat().st_mtime_ns
    except OSError:
        return 0
