"""User choices made at install time, read by the hook on every event and by the host on every poll."""
import copy
import json

from . import paths

DEFAULTS = {
    "notifications": False,
    "sound": True,
    "agents": [],  # ids of the agents being watched (their hooks are installed)
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
    path = paths.config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def mtime():
    """When config.json last changed, or 0 when it doesn't exist. Lets the host reload it only on change."""
    try:
        return paths.config_file().stat().st_mtime_ns
    except OSError:
        return 0
