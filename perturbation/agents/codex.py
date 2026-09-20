"""Codex CLI: hooks in ~/.codex/hooks.json, a file of its own.

Codex runs a hook only after the user trusts it with /hooks, and remembers that trust by the hook's
position in the file and a hash of its definition. So a reinstall rewrites our hooks where they already
are, with the same command and timeout, and Codex keeps trusting them.
"""
import os
import shutil

from . import jsonfile
from .base import (
    BUSY,
    CONFIG,
    MARKER,
    NEEDS_YOU,
    READY,
    WAITING,
    Check,
    Notice,
    Update,
    describe,
    home,
    project_of,
    session_id,
    summarize,
)

ID = "codex"
NAME = "Codex CLI"
SHORT = "Codex"
SHAPE = CONFIG
ORDER = 2

# Event -> state to record; None removes the session. Subagents report their parent's session_id, so
# their tool events keep the parent busy.
EVENTS = {
    "SessionStart": READY,
    "UserPromptSubmit": BUSY,
    "PreToolUse": BUSY,
    "PostToolUse": BUSY,
    "PermissionRequest": WAITING,
    "Stop": READY,
    "Interrupt": READY,
    "SessionEnd": None,
}

# Codex gives these events 1 s by default and at most 3 s. A login shell plus Python can need more than 1 s.
SHORT_EVENTS = ("SessionEnd", "Interrupt")
TIMEOUT_SECONDS = 5
SHORT_TIMEOUT_SECONDS = 3

# PermissionRequest fires before Codex decides who approves, so also for calls it approves itself. A
# session still untouched this long afterwards is really waiting for you.
APPROVAL_GRACE_SECONDS = float(os.environ.get("PERTURBATION_APPROVAL_GRACE_SECONDS", 5))


def codex_home():
    return home("CODEX_HOME", ".codex")


def hooks_path():
    return codex_home() / "hooks.json"


def detect():
    if codex_home().is_dir():
        return f"found {describe(codex_home())}"
    if shutil.which("codex"):
        return "found codex on PATH"
    return None


def per_event_commands():
    return False


def handler(event, command):
    timeout = SHORT_TIMEOUT_SECONDS if event in SHORT_EVENTS else TIMEOUT_SECONDS
    return {"type": "command", "command": command, "timeout": timeout}


def install(commands):
    """Returns the hooks file. `changed(commands)` says whether the file was touched, which decides
    whether the user has to trust the hooks again."""
    _rewrite(commands.hook(), (MARKER,))
    return hooks_path()


def changed(commands):
    """True when a fresh install would change the file, so Codex would ask for trust again."""
    try:
        data = jsonfile.read(hooks_path())
    except jsonfile.ConfigError:
        return True
    before = jsonfile.json.dumps(data, sort_keys=True)
    _change(data, commands.hook(), (MARKER,))
    return jsonfile.json.dumps(data, sort_keys=True) != before


def uninstall(markers=(MARKER,)):
    _rewrite(None, markers)


def _rewrite(command, markers):
    return jsonfile.update(
        hooks_path(),
        lambda data: _change(data, command, markers),
        skip_if_missing=command is None,
        delete_when_empty=True,
    )


def _change(data, command, markers):
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise jsonfile.ConfigError(f"{hooks_path()} has a `hooks` key that is not an object. Left it untouched.")
    for event in list(hooks) + [e for e in EVENTS if e not in hooks]:
        ours = handler(event, command) if command and event in EVENTS else None
        groups = []
        for group in hooks.get(event, []):
            if not isinstance(group, dict):
                groups.append(group)
                continue
            handlers = []
            for h in group.get("hooks", []):
                if not jsonfile.command_matches(h, markers):
                    handlers.append(h)
                elif ours:
                    handlers.append(ours)  # same place, so Codex keeps trusting it
                    ours = None
            if handlers:
                groups.append({**group, "hooks": handlers})
        if ours:
            groups.append({"hooks": [ours]})
        if groups:
            hooks[event] = groups
        else:
            hooks.pop(event, None)
    if not hooks:
        del data["hooks"]


def installed(markers=(MARKER,)):
    try:
        hooks = jsonfile.read(hooks_path()).get("hooks")
    except jsonfile.ConfigError:
        return None
    count = jsonfile.count_groups(hooks, markers) if isinstance(hooks, dict) else 0
    return f"{count} hook entries in {describe(hooks_path())}" if count else None


def hooks_disabled():
    """True if ~/.codex/config.toml turns hooks off with `[features] hooks = false`."""
    try:
        text = (codex_home() / "config.toml").read_text(encoding="utf-8")
    except OSError:
        return False
    table = ""
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line.startswith("["):
            table = line.strip("[] ").replace(" ", "")
            continue
        key, found, value = line.partition("=")
        key = key.strip().replace(" ", "")
        if found and f"{table}.{key}".lstrip(".") in ("features.hooks", "features.codex_hooks"):
            return value.strip() == "false"
    return False


def verify():
    return "/hooks inside Codex lists them; trust the perturbation hooks there or Codex skips them"


def parse(event, payload):
    event = payload.get("hook_event_name")
    if event not in EVENTS:
        return None
    session = session_id(payload.get("session_id"))
    project = project_of(payload.get("cwd"))
    value = EVENTS[event]
    if value is None:
        return Update(session, None)
    if event == "Stop":
        message = summarize(payload.get("last_assistant_message")) or "Task finished"
        return Update(session, READY, Notice(READY, message), project)
    if event == "PermissionRequest":
        return Update(session, WAITING, Notice(NEEDS_YOU, _approval_message(payload)), project, delay=APPROVAL_GRACE_SECONDS)
    return Update(session, value, project=project)


def _approval_message(payload):
    # PermissionRequest has no message field, so describe the tool that is waiting for approval.
    tool = payload.get("tool_name") or "a tool"
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if isinstance(command, list):
        command = " ".join(str(part) for part in command)
    if tool == "Bash" and command:
        return f"Wants to run: {summarize(command)}"
    if tool == "apply_patch":
        return "Wants to edit files"
    return f"Wants to use {tool}"


def doctor(commands):
    try:
        data = jsonfile.read(hooks_path())
    except jsonfile.ConfigError as error:
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
    checks = [Check(len(ours) == len(EVENTS), f"{len(ours)} of {len(EVENTS)} events registered in {describe(hooks_path())}")]
    stale = [h for h in ours if h.get("command") != commands.hook()]
    checks.append(Check(not stale, "hook command points at the installed app" if not stale else f"{len(stale)} entries use an old command; run the installer again"))
    checks.append(Check(not hooks_disabled(), "hooks are enabled in config.toml" if not hooks_disabled() else f"hooks are turned off in {describe(codex_home() / 'config.toml')}: remove `hooks = false` under [features]"))
    checks.append(Check(True, "trust can only be seen from inside Codex: run /hooks there"))
    return checks
