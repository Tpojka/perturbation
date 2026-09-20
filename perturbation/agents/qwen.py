"""Qwen Code: hooks merged into ~/.qwen/settings.json.

Qwen Code forked Gemini CLI but its hooks are Claude-shaped: `hook_event_name`, `session_id` and `cwd`
in every payload, a nested {matcher, hooks: [...]} table under `hooks`, timeouts in seconds, exit 2 as
a blocking error. Anything a hook prints on exit 0 is added to the model's context on some events, so
printing nothing is not optional. A `shell` field picks bash or PowerShell per hook.

Verified against docs/users/features/hooks.md in QwenLM/qwen-code on 2026-09-20.
"""
import shutil

from . import jsonfile
from .base import (
    BUSY,
    CONFIG,
    FREE,
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

ID = "qwen"
NAME = "Qwen Code"
SHORT = "Qwen"
SHAPE = CONFIG
TIER = FREE
ORDER = 7

TIMEOUT_SECONDS = 5  # seconds; Qwen reads 1000 and above as milliseconds

NEEDS_YOU_TYPES = ("permission_prompt",)
IDLE = "idle_prompt"

# Event -> matcher to register with (None: every occurrence).
EVENTS = {
    "SessionStart": None,
    "UserPromptSubmit": None,
    "PreToolUse": "*",
    "PostToolUse": "*",
    "PostToolUseFailure": "*",
    "Notification": "|".join(NEEDS_YOU_TYPES + (IDLE,)),
    "PermissionRequest": "*",
    "Stop": None,
    "StopFailure": None,
    "PreCompact": "manual|auto",
    "PostCompact": "manual|auto",
    "SessionEnd": None,
}


def config_home():
    return home(None, ".qwen")


def settings_path():
    return config_home() / "settings.json"


def detect():
    if config_home().is_dir():
        return f"found {describe(config_home())}"
    if shutil.which("qwen"):
        return "found qwen on PATH"
    return None


def per_event_commands():
    return False


def entry(commands):
    item = {"type": "command", "command": commands.hook(), "name": "perturbation", "timeout": TIMEOUT_SECONDS}
    if commands.shell == "powershell":
        item["shell"] = "powershell"
    return item


def install(commands):
    def change(data):
        hooks = data.setdefault("hooks", {})
        if not isinstance(hooks, dict):
            raise ConfigError(f"{settings_path()} has a `hooks` key that is not an object. Left it untouched.")
        jsonfile.strip_groups(hooks, (MARKER,))
        for event, matcher in EVENTS.items():
            group = {"matcher": matcher} if matcher else {}
            group["hooks"] = [entry(commands)]
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
    return "/hooks inside Qwen Code lists them"


def parse(event, payload):
    event = payload.get("hook_event_name")
    session = session_id(payload.get("session_id"))
    project = project_of(payload.get("cwd"))
    if event == "SessionStart":
        return Update(session, READY, project=project)
    if event in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure", "PreCompact"):
        return Update(session, BUSY, project=project)
    if event == "Notification":
        kind = payload.get("notification_type")
        if kind in NEEDS_YOU_TYPES:
            return Update(session, WAITING, Notice(NEEDS_YOU, payload.get("message") or "Qwen is waiting for you"), project)
        return Update(session, READY, project=project) if kind == IDLE else None
    if event == "PermissionRequest":
        return Update(session, WAITING, Notice(NEEDS_YOU, _permission(payload)), project)
    if event == "Stop":
        message = summarize(payload.get("last_assistant_message")) or "Task finished"
        return Update(session, READY, Notice(READY, message), project)
    if event == "StopFailure":
        kind = str(payload.get("error") or "error")
        details = summarize(payload.get("error_details"))
        return Update(session, READY, Notice(STOPPED, f"{kind}: {details}" if details else kind), project)
    if event == "PostCompact":
        if payload.get("trigger") == "auto":
            return Update(session, BUSY, project=project)
        return Update(session, READY, Notice(READY, "Context compacted"), project)
    if event == "SessionEnd":
        return Update(session, None)
    return None


def _permission(payload):
    tool = payload.get("tool_name") or "a tool"
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if tool == "run_shell_command" and command:
        return f"Wants to run: {summarize(str(command))}"
    return f"Wants to use {tool}"


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
        checks.append(Check(False, "disableAllHooks is set in settings.json, so Qwen Code runs no hooks at all"))
    return checks
