"""Goose: a plugin directory of our own, ~/.agents/plugins/perturbation/, holding hooks/hooks.json.

Goose discovers plugins on disk (Open Plugins format) and runs every hook command through `sh -c`, on
every OS, with the event payload as JSON on stdin. The payload names the event (`event`) and the session
(`session_id`); `working_dir` arrives on tool events and `last_assistant_message` on Stop. There is no
permission or notification event, so Goose has no waiting state.

Verified against crates/goose/src/hooks/mod.rs and documentation/docs/guides/context-engineering/ in
aaif-goose/goose on 2026-09-20.
"""
import json
import shutil
from pathlib import Path

from . import jsonfile
from .base import BUSY, CONFIG, FREE, MARKER, READY, Check, Notice, Update, describe, project_of, session_id, summarize

ID = "goose"
NAME = "Goose"
SHORT = "Goose"
SHAPE = CONFIG
TIER = FREE
ORDER = 6

SHELL = "sh"  # Goose runs hooks with `sh -c` on every OS, so the command is POSIX even on Windows
TIMEOUT_SECONDS = 5

# Event -> state to record; None removes the session. Stop can block the turn (exit 2 or a decision on
# stdout); our hook prints nothing and exits 0, which Goose reads as allow.
EVENTS = {
    "SessionStart": READY,
    "UserPromptSubmit": BUSY,
    "PreToolUse": BUSY,
    "PostToolUse": BUSY,
    "PostToolUseFailure": BUSY,
    "BeforeShellExecution": BUSY,
    "AfterShellExecution": BUSY,
    "BeforeReadFile": BUSY,
    "AfterFileEdit": BUSY,
    "Stop": READY,
    "SessionEnd": None,
}


def config_home():
    return Path.home() / ".config" / "goose"


def plugins_dir():
    return Path.home() / ".agents" / "plugins"


def plugin_dir(marker=MARKER):
    return plugins_dir() / marker.split(".")[0]


def hooks_path(marker=MARKER):
    return plugin_dir(marker) / "hooks" / "hooks.json"


def manifest_path(marker=MARKER):
    return plugin_dir(marker) / "plugin.json"


def settings_path():
    return config_home() / "settings.json"


def detect():
    if config_home().is_dir():
        return f"found {describe(config_home())}"
    if shutil.which("goose"):
        return "found goose on PATH"
    return None


def per_event_commands():
    return False


def content(commands):
    entry = {"type": "command", "command": commands.hook(shell=SHELL), "timeout": TIMEOUT_SECONDS}
    return {"hooks": {event: [{"hooks": [entry]}] for event in EVENTS}}


def manifest():
    return {"name": plugin_dir().name, "version": "1", "description": "Perturbation: shows Goose's status in Chrome's toolbar"}


def install(commands):
    jsonfile.write(manifest_path(), manifest())
    jsonfile.write(hooks_path(), content(commands))
    return hooks_path()


def uninstall(markers=(MARKER,)):
    for marker in markers:
        shutil.rmtree(plugin_dir(marker), ignore_errors=True)


def installed(markers=(MARKER,)):
    for marker in markers:
        if hooks_path(marker).is_file():
            return describe(plugin_dir(marker))
    return None


def disabled():
    """True when Goose's settings list our plugin under disabledPlugins."""
    try:
        settings = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    listed = settings.get("disabledPlugins") if isinstance(settings, dict) else None
    return isinstance(listed, list) and plugin_dir().name in listed


def verify():
    return "goose session; a file appears under sessions/goose/ in the data directory"


def parse(event, payload):
    event = payload.get("event")
    if event not in EVENTS:
        return None
    session = session_id(payload.get("session_id"))
    project = project_of(payload.get("working_dir"))
    value = EVENTS[event]
    if value is None:
        return Update(session, None)
    if event == "Stop":
        message = summarize(payload.get("last_assistant_message")) or "Task finished"
        return Update(session, READY, Notice(READY, message), project)
    return Update(session, value, project=project)


def doctor(commands):
    if not hooks_path().is_file():
        return [Check(False, f"{describe(hooks_path())} is missing")]
    try:
        data = jsonfile.read(hooks_path())
    except jsonfile.ConfigError as error:
        return [Check(False, str(error))]
    current = data == content(commands)
    return [
        Check(True, f"{describe(hooks_path())} is present"),
        Check(current, "hooks are current" if current else "hooks differ from what this version writes; run the installer again"),
        Check(manifest_path().is_file(), f"{describe(manifest_path())} {'is present' if manifest_path().is_file() else 'is missing'}"),
        Check(not disabled(), "plugin is enabled" if not disabled() else f"plugin is listed under disabledPlugins in {describe(settings_path())}"),
    ]
