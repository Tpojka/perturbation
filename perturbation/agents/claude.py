"""Claude Code: hooks merged into ~/.claude/settings.json, the file it shares with everything else.

Claude names the event in the payload (`hook_event_name`), so one command serves every event.
"""
import shutil

from . import jsonfile
from .base import (
    BUSY,
    CONFIG,
    MARKER,
    NEEDS_YOU,
    READY,
    STOPPED,
    WAITING,
    Check,
    ConfigError,
    Notice,
    Update,
    describe,
    home,
    project_of,
    session_id,
    summarize,
)

ID = "claude"
NAME = "Claude Code"
SHORT = "Claude"
SHAPE = CONFIG
ORDER = 1

TIMEOUT_SECONDS = 5

# Notification types that mean Claude is blocked on you. `idle_prompt` only repeats a finished turn.
NEEDS_YOU_TYPES = ("permission_prompt", "elicitation_dialog", "elicitation_url_dialog", "agent_needs_input")
IDLE = "idle_prompt"

# Event -> matcher to register with (None: every occurrence).
EVENTS = {
    "SessionStart": None,
    "UserPromptSubmit": None,
    "PreToolUse": "*",
    "PostToolUse": "*",
    "Notification": "|".join(NEEDS_YOU_TYPES + (IDLE,)),
    "Stop": None,
    "StopFailure": None,
    "PreCompact": "manual|auto",
    "PostCompact": "manual|auto",
    "SessionEnd": None,
}


def config_home():
    return home("CLAUDE_CONFIG_DIR", ".claude")


def settings_path():
    return config_home() / "settings.json"


def detect():
    if config_home().is_dir():
        return f"found {describe(config_home())}"
    if shutil.which("claude"):
        return "found claude on PATH"
    return None


def per_event_commands():
    return False


def entry(command):
    return {"type": "command", "command": command, "timeout": TIMEOUT_SECONDS}


def install(commands):
    """Merge our groups into the `hooks` table, replacing any earlier ones of ours. Every other key and
    every other hook stays as it was, and the file is backed up first."""
    command = commands.hook()

    def change(data):
        hooks = data.setdefault("hooks", {})
        if not isinstance(hooks, dict):
            raise ConfigError(f"{settings_path()} has a `hooks` key that is not an object. Left it untouched.")
        jsonfile.strip_groups(hooks, (MARKER,))
        for event, matcher in EVENTS.items():
            group = {"matcher": matcher} if matcher else {}
            group["hooks"] = [entry(command)]
            hooks.setdefault(event, []).append(group)

    jsonfile.update(settings_path(), change)
    return settings_path()


def uninstall(markers=(MARKER,)):
    def change(data):
        hooks = data.get("hooks")
        if isinstance(hooks, dict):
            jsonfile.strip_groups(hooks, markers)
            if not hooks:
                del data["hooks"]

    jsonfile.update(settings_path(), change, skip_if_missing=True)


def installed(markers=(MARKER,)):
    try:
        hooks = jsonfile.read(settings_path()).get("hooks")
    except ConfigError:
        return None
    count = jsonfile.count_groups(hooks, markers) if isinstance(hooks, dict) else 0
    return f"{count} hook entries in {describe(settings_path())}" if count else None


def verify():
    return "/hooks inside Claude Code lists them"


def parse(event, payload):
    event = payload.get("hook_event_name")
    session = session_id(payload.get("session_id"))
    project = project_of(payload.get("cwd"))
    if event == "SessionStart":
        return Update(session, READY, project=project)
    if event in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "PreCompact"):
        return Update(session, BUSY, project=project)
    if event == "Notification":
        return _notification(session, payload, project)
    if event == "Stop":
        message = summarize(payload.get("last_assistant_message")) or "Task finished"
        return Update(session, READY, Notice(READY, message), project)
    if event == "StopFailure":
        return Update(session, READY, Notice(STOPPED, _error(payload)), project)
    if event == "PostCompact":
        # A manual /compact ends with Claude waiting for you; an automatic one happens mid-turn and Claude carries on.
        if payload.get("trigger") == "auto":
            return Update(session, BUSY, project=project)
        return Update(session, READY, Notice(READY, "Context compacted"), project)
    if event == "SessionEnd":
        return Update(session, None)
    return None


def _notification(session, payload, project):
    kind = payload.get("notification_type")
    message = payload.get("message") or ""
    if not kind:  # older payloads name no type; the idle reminder is recognisable by its text
        kind = IDLE if "waiting for your input" in message else "permission_prompt"
    if kind in NEEDS_YOU_TYPES:
        return Update(session, WAITING, Notice(NEEDS_YOU, message or "Claude is waiting for you"), project)
    if kind == IDLE:
        return Update(session, READY, project=project)
    return None


def _error(payload):
    kind = str(payload.get("error_type") or "error")
    message = summarize(payload.get("error_message"))
    return f"{kind}: {message}" if message else kind


def doctor(commands):
    try:
        data = jsonfile.read(settings_path())
    except ConfigError as error:
        return [Check(False, str(error))]
    hooks = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}
    ours = [
        h
        for groups in hooks.values()
        if isinstance(groups, list)
        for group in groups
        if isinstance(group, dict)
        for h in group.get("hooks", [])
        if jsonfile.command_matches(h, (MARKER,))
    ]
    checks = [Check(len(ours) == len(EVENTS), f"{len(ours)} of {len(EVENTS)} events registered in {describe(settings_path())}")]
    stale = [h for h in ours if h.get("command") != commands.hook()]
    checks.append(Check(not stale, "hook command points at the installed app" if not stale else f"{len(stale)} entries use an old command; run the installer again"))
    if data.get("disableAllHooks"):
        checks.append(Check(False, "disableAllHooks is set in settings.json, so Claude Code runs no hooks at all"))
    return checks
