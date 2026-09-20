"""opencode: a JavaScript plugin file, ~/.config/opencode/plugins/perturbation.js, the only agent here
that is not a shell-hook system.

opencode runs plugins in its own runtime and publishes events on a bus. Our plugin (`assets/
opencode-plugin.js`) forwards the events below to `perturbation.pyz hook opencode`, with the event JSON
on stdin, from a detached process it never waits for. Event shapes follow @opencode-ai/sdk 1.18.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

from .base import BUSY, FREE, MARKER, NEEDS_YOU, PLUGIN, READY, STOPPED, WAITING, Check, Notice, Update, describe, project_of

ID = "opencode"
NAME = "opencode"
SHORT = "opencode"
SHAPE = PLUGIN
TIER = FREE
ORDER = 5

TEMPLATE = Path(__file__).with_name("assets") / "opencode-plugin.js"

# session.status carries {"type": "busy" | "idle" | "retry"}.
STATUS = {"busy": BUSY, "retry": BUSY, "idle": READY}
# Pressing Esc aborts a turn; that is not an error worth a notification.
ABORTED = "MessageAbortedError"


def config_home():
    override = os.environ.get("OPENCODE_CONFIG_DIR")
    if override:
        return Path(override)
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "opencode"


def plugin_path(marker=MARKER):
    return config_home() / "plugins" / (marker.split(".")[0] + ".js")


def detect():
    if config_home().is_dir():
        return f"found {describe(config_home())}"
    if shutil.which("opencode"):
        return "found opencode on PATH"
    return None


def per_event_commands():
    return False


def content(commands):
    """The plugin file: the template with the interpreter and app paths baked in, so nothing is looked
    up at runtime."""
    source = TEMPLATE.read_text(encoding="utf-8")
    return source.replace("__PYTHON__", json.dumps(commands.python)).replace("__APP__", json.dumps(str(commands.app)))


def install(commands):
    path = plugin_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".perturbation.tmp")
    tmp.write_text(content(commands), encoding="utf-8")
    os.replace(tmp, path)
    return path


def uninstall(markers=(MARKER,)):
    for marker in markers:
        try:
            plugin_path(marker).unlink()
        except FileNotFoundError:
            pass


def installed(markers=(MARKER,)):
    for marker in markers:
        path = plugin_path(marker)
        try:
            if marker in path.read_text(encoding="utf-8"):
                return describe(path)
        except OSError:
            pass
    return None


def verify():
    return "start opencode; a file appears under sessions/opencode/ in the data directory"


def parse(event, payload):
    kind = payload.get("type")
    props = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}
    info = props.get("info") if isinstance(props.get("info"), dict) else {}
    session = props.get("sessionID") or info.get("id")
    if not session:
        return None
    session = str(session)
    project = project_of(info.get("directory"))
    if kind == "session.created":
        return None if info.get("parentID") else Update(session, READY, project=project)
    if kind == "session.status":
        status = props.get("status") if isinstance(props.get("status"), dict) else {}
        value = STATUS.get(status.get("type"))
        return Update(session, value) if value else None
    if kind in ("tool.execute.before", "tool.execute.after", "permission.replied", "message.updated"):
        return Update(session, BUSY)
    if kind == "session.idle":
        return Update(session, READY, Notice(READY, "Task finished"))
    if kind == "session.error":
        error = props.get("error") if isinstance(props.get("error"), dict) else {}
        if error.get("name") == ABORTED:
            return Update(session, READY)
        return Update(session, READY, Notice(STOPPED, _error(error)))
    if kind in ("permission.updated", "permission.asked"):
        return Update(session, WAITING, Notice(NEEDS_YOU, _permission(props)))
    if kind in ("session.deleted", "perturbation.shutdown"):
        return Update(session, None)
    return None


def _permission(props):
    title = props.get("title")
    if title:
        return str(title)
    return f"Wants to use {props.get('type') or 'a tool'}"


def _error(error):
    name = str(error.get("name") or "error")
    data = error.get("data") if isinstance(error.get("data"), dict) else {}
    message = str(data.get("message") or "")
    return f"{name}: {message}" if message else name


def doctor(commands):
    path = plugin_path()
    if not path.is_file():
        return [Check(False, f"{describe(path)} is missing")]
    checks = [Check(True, f"{describe(path)} is present")]
    try:
        current = path.read_text(encoding="utf-8") == content(commands)
    except OSError:
        current = False
    checks.append(Check(current, "plugin is current" if current else "plugin differs from what this version writes; run the installer again"))
    node = shutil.which("node")
    if node:
        try:
            result = subprocess.run([node, "--check", str(path)], capture_output=True, text=True, timeout=30)
            checks.append(Check(result.returncode == 0, "plugin parses (node --check)" if result.returncode == 0 else f"plugin does not parse: {result.stderr.strip()[:200]}"))
        except (OSError, subprocess.SubprocessError):
            pass
    return checks
