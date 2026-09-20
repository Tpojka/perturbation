"""Antigravity CLI: one bundle in ~/.gemini/config/hooks.json, and optionally its status line.

Both files belong to Antigravity: the hooks file is shared with the /hooks command, the Antigravity 2.0
app and the IDE, and the settings file is written sparsely by the CLI itself. So both are merged key by
key, backed up first, and never rewritten whole.

Antigravity's hook payload carries no event name, so each event registers its own argv token
(`hook antigravity busy`, `hook antigravity stop`). Its stdout is parsed as a decision, so the hook prints
nothing, ever.
"""
import os
import shutil
from pathlib import Path

from . import jsonfile
from .base import BUSY, CONFIG, MARKER, PRO, NEEDS_YOU, READY, WAITING, Check, Notice, Update, describe, project_of, session_id

ID = "antigravity"
NAME = "Antigravity CLI"
SHORT = "Antigravity"
SHAPE = CONFIG
TIER = PRO
ORDER = 4

TIMEOUT_SECONDS = 5
MATCHER = ".*"

# Event -> argv token. PreToolUse and PostToolUse take matcher groups; the rest take a flat list.
FLAT_EVENTS = {"PreInvocation": "busy", "PostInvocation": "busy", "Stop": "stop"}
TOOL_EVENTS = {"PreToolUse": "busy", "PostToolUse": "busy"}

# Status line: agent_state -> recorded state. An open confirmation dialog outranks all of them.
AGENT_STATES = {"thinking": BUSY, "working": BUSY, "tool_use": BUSY, "idle": READY, "initializing": READY}
LABELS = {BUSY: "working", WAITING: "needs you", READY: "ready"}


def gemini_home():
    return Path.home() / ".gemini"


def cli_home():
    return gemini_home() / "antigravity-cli"


def hooks_path():
    return gemini_home() / "config" / "hooks.json"


def settings_path():
    return cli_home() / "settings.json"


def bundle_key(marker=MARKER):
    """hooks.json is keyed by bundle name; ours is the app's name (a predecessor's was its own)."""
    return marker.split(".")[0]


def detect():
    if cli_home().is_dir():
        return f"found {describe(cli_home())}"
    if shutil.which("agy"):
        return "found agy on PATH"
    return None


def per_event_commands():
    return True


def bundle(commands):
    entry = lambda token: {"type": "command", "command": commands.hook(token), "timeout": TIMEOUT_SECONDS}
    hooks = {event: [entry(token)] for event, token in FLAT_EVENTS.items()}
    hooks.update({event: [{"matcher": MATCHER, "hooks": [entry(token)]}] for event, token in TOOL_EVENTS.items()})
    return hooks


def install(commands):
    jsonfile.update(hooks_path(), lambda data: data.update({bundle_key(): bundle(commands)}))
    return hooks_path()


def uninstall(markers=(MARKER,)):
    keys = [bundle_key(m) for m in markers]
    jsonfile.update(hooks_path(), lambda data: [data.pop(k, None) for k in keys], skip_if_missing=True)
    uninstall_statusline(markers)


def installed(markers=(MARKER,)):
    try:
        data = jsonfile.read(hooks_path())
    except jsonfile.ConfigError:
        return None
    for marker in markers:
        if bundle_key(marker) in data:
            return f"bundle {bundle_key(marker)!r} in {describe(hooks_path())}"
    return None


def verify():
    return 'agy -p "/hooks" --output-format json'


def parse(event, payload):
    session = session_id(payload.get("conversationId"))
    workspaces = payload.get("workspacePaths")
    project = project_of(workspaces[0] if isinstance(workspaces, list) and workspaces else None)
    if event == "busy":
        return Update(session, BUSY, project=project)
    if event == "stop":
        # Stop fires whenever the execution loop terminates, including intermediate stops that carry on.
        if not payload.get("fullyIdle"):
            return None
        return Update(session, READY, Notice(READY, "Task finished"), project)
    return None


# --- status line: the only source of "needs you" for this agent ---------------------------------


def statusline_owner(settings=None, markers=(MARKER,)):
    """Who owns the status line: None if free, "ours" if ours, "other" if someone else's."""
    if settings is None:
        try:
            settings = jsonfile.read(settings_path())
        except jsonfile.ConfigError:
            return "other"  # unreadable, so treat it as taken and keep our hands off
    block = settings.get("statusLine")
    command = block.get("command") if isinstance(block, dict) else None
    if not command:
        return None
    return "ours" if any(m in str(command) for m in markers) else "other"


def install_statusline(command):
    """Add our statusLine block, keeping Antigravity's own line above ours."""

    def change(data):
        data["statusLine"] = {"type": "command", "command": command, "enabled": True, "stack_with_default": True}

    jsonfile.update(settings_path(), change)


def uninstall_statusline(markers=(MARKER,)):
    def change(data):
        if statusline_owner(data, markers) == "ours":
            del data["statusLine"]

    jsonfile.update(settings_path(), change, skip_if_missing=True)


def statusline(payload):
    session = session_id(payload.get("conversation_id"), payload.get("session_id"))
    workspace = payload.get("workspace")
    current_dir = workspace.get("current_dir") if isinstance(workspace, dict) else None
    project = project_of(current_dir, payload.get("cwd"), os.getcwd())
    if payload.get("tool_confirmation_pending"):
        update = Update(session, WAITING, Notice(NEEDS_YOU, "Waiting for your confirmation"), project)
    else:
        # "ready" belongs to the Stop hook, which already notifies for it, so no notice here.
        update = Update(session, AGENT_STATES.get(payload.get("agent_state"), READY), project=project)
    return update, LABELS[update.state]


def doctor(commands):
    try:
        data = jsonfile.read(hooks_path())
    except jsonfile.ConfigError as error:
        return [Check(False, str(error))]
    ours = data.get(bundle_key())
    checks = [Check(isinstance(ours, dict), f"bundle {bundle_key()!r} in {describe(hooks_path())}" if ours else f"bundle {bundle_key()!r} missing from {describe(hooks_path())}")]
    if isinstance(ours, dict):
        current = ours == bundle(commands)
        checks.append(Check(current, "bundle is current" if current else "bundle differs from what this version writes; run the installer again"))
    owner = statusline_owner()
    checks.append(Check(True, {None: "status line is free", "ours": "status line is ours", "other": "status line belongs to someone else"}[owner]))
    return checks
