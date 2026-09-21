"""GitHub Copilot CLI: our own hook file, ~/.copilot/hooks/perturbation.json.

Copilot loads every *.json file in that folder, and so does Copilot's agent in VS Code. The file holds
only our hooks, so there is nothing to merge with and nothing to back up.
"""
import shutil

from . import jsonfile
from .base import BUSY, CONFIG, MARKER, PRO, NEEDS_YOU, READY, STOPPED, WAITING, Check, Notice, Update, describe, home, project_of, session_id

ID = "copilot"
NAME = "GitHub Copilot CLI"
SHORT = "Copilot"
SHAPE = CONFIG
TIER = PRO
ORDER = 3

TIMEOUT_SECONDS = 5

# Notification types that mean Copilot is waiting for you. The others report background shells and agents.
NEEDS_YOU_TYPES = ("permission_prompt", "elicitation_dialog")

# Event to register -> matcher. PascalCase names give the payload we read (hook_event_name, session_id).
# Notifications exist only as camelCase `notification`; that payload has hook_event_name plus sessionId.
EVENTS = {
    "SessionStart": None,
    "UserPromptSubmit": None,
    "PreToolUse": None,
    "PostToolUse": None,
    "PostToolUseFailure": None,
    "notification": "|".join(NEEDS_YOU_TYPES),
    "ErrorOccurred": None,
    "Stop": None,
    "SessionEnd": None,
}


def copilot_home():
    return home("COPILOT_HOME", ".copilot")


def hooks_path(marker=MARKER):
    return copilot_home() / "hooks" / (marker.split(".")[0] + ".json")


def detect():
    if copilot_home().is_dir():
        return f"found {describe(copilot_home())}"
    if shutil.which("copilot"):
        return "found copilot on PATH"
    return None


def per_event_commands():
    return False


def content(commands):
    """The whole hook file. The command goes in the `bash` field on macOS and Linux, `powershell` on Windows."""
    hooks = {}
    for event, matcher in EVENTS.items():
        entry = {"type": "command", commands.shell: commands.hook(), "timeoutSec": TIMEOUT_SECONDS}
        if matcher:
            entry["matcher"] = matcher
        hooks[event] = [entry]
    return {"version": 1, "hooks": hooks}


def install(commands):
    jsonfile.write(hooks_path(), content(commands))
    return hooks_path()


def uninstall(markers=(MARKER,)):
    for marker in markers:
        try:
            hooks_path(marker).unlink()
        except FileNotFoundError:
            pass


def installed(markers=(MARKER,)):
    for marker in markers:
        if hooks_path(marker).is_file():
            return describe(hooks_path(marker))
    return None


def verify():
    return "restart Copilot CLI; the file is read at startup"


def parse(event, payload):
    event = payload.get("hook_event_name")
    # PascalCase events send session_id; the notification event sends sessionId.
    session = session_id(payload.get("session_id"), payload.get("sessionId"))
    project = project_of(payload.get("cwd"))
    if event == "SessionStart":
        return Update(session, READY, project=project)
    if event in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure"):
        return Update(session, BUSY, project=project)
    if event == "Notification":
        if payload.get("notification_type") not in NEEDS_YOU_TYPES:
            return None
        return Update(session, WAITING, Notice(NEEDS_YOU, payload.get("message") or "Copilot is waiting for you"), project)
    if event == "ErrorOccurred":
        # Copilot retries recoverable errors. Any other error ends the turn, possibly without a Stop.
        if payload.get("recoverable") is not False:
            return None
        return Update(session, READY, Notice(STOPPED, _error(payload)), project)
    if event == "Stop":
        return Update(session, READY, Notice(READY, "Task finished"), project)
    if event == "SessionEnd":
        return Update(session, None)
    return None


def _error(payload):
    error = payload.get("error")
    if isinstance(error, dict):
        name, message = error.get("name"), error.get("message")
        return f"{name}: {message}" if name and message else str(message or name or "error")
    return str(error or payload.get("message") or "error")


def doctor(commands):
    path = hooks_path()
    if not path.is_file():
        return [Check(False, f"{describe(path)} is missing")]
    try:
        data = jsonfile.read(path)
    except jsonfile.ConfigError as error:
        return [Check(False, str(error))]
    current = data == content(commands)
    return [
        Check(True, f"{describe(path)} is present"),
        Check(current, "hook file is current" if current else "hook file differs from what this version writes; run the installer again"),
    ]
