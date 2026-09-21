"""The adapter contract. Every agent is one module in this package, and nothing else in the codebase
knows an agent exists.

A module is an adapter when it has these attributes (checked by the registry on import):

    ID       = "codex"           directory under sessions/, argv token, config key
    NAME     = "Codex CLI"       shown in the popup and the installer
    SHORT    = "Codex"           notification titles: "Codex is ready · project"
    SHAPE    = "config"          "config": we write entries into its hooks file; "plugin": we drop a plugin file
    ORDER    = 2                 default position in the popup and the installer
    TIER     = "pro"             "pro": a paid agent; "free": a free-tier one, listed after the pro tier

    def detect() -> Optional[str]
        What was found when the agent looks installed ("~/.codex", "codex on PATH"), else None.

    def per_event_commands() -> bool
        True when the payload carries no event name, so each event registers its own argv token.

    def install(commands) -> Path
        Write this agent's hook configuration or plugin file and return the path written.
        `commands.hook(event=None)` is the OS-specific shell command, already hardened to exit 0;
        `commands.statusline()` the status line command; `commands.shell` is "bash" or "powershell".

    def uninstall(markers=(MARKER,)) -> None
        Remove only what install() wrote. `markers` identify our entries; the migration passes a
        predecessor's markers to remove its entries the same way.

    def installed(markers=(MARKER,)) -> Optional[str]
        Where our entry is ("9 hook entries in ~/.codex/hooks.json"), or None.

    def verify() -> Optional[str]
        What the user can run to confirm the registration, printed by the installer.

    def parse(event, payload) -> Optional[Update]
        Turn one hook payload into an Update, or None to ignore it.

    def doctor(commands) -> List[Check]
        Agent-specific health checks for `python3 -m perturbation.install doctor`.

    def statusline(payload) -> Optional[Tuple[Optional[Update], str]]      (optional)
        For agents whose TUI runs a status line command: the update to record and the text to show.
"""
import os
from pathlib import Path
from typing import List, NamedTuple, Optional

from .. import state

MARKER = "perturbation.pyz"  # every command we write contains this, so we can find and remove our entries

BUSY = state.BUSY
WAITING = state.WAITING
READY = state.READY

# Notice kinds: what the notification says.
NEEDS_YOU = "needs_you"
STOPPED = "stopped"
# READY is a notice kind too ("{Short} is ready").

CONFIG = "config"
PLUGIN = "plugin"

PRO = "pro"
FREE = "free"

REQUIRED = ("ID", "NAME", "SHORT", "SHAPE", "ORDER", "TIER", "detect", "per_event_commands", "install", "uninstall", "installed", "verify", "parse", "doctor")


class Notice(NamedTuple):
    kind: str  # READY | NEEDS_YOU | STOPPED
    message: str  # the notification body


class Update(NamedTuple):
    session_id: str
    state: Optional[str]  # BUSY | WAITING | READY | None (None removes the session)
    notice: Optional[Notice] = None  # sent only when the stored state changes
    project: Optional[str] = None  # named in the notification title
    delay: float = 0.0  # seconds to wait before applying, dropped if the session changes meanwhile

    def to_json(self):
        data = self._asdict()
        data["notice"] = list(self.notice) if self.notice else None
        return data

    @classmethod
    def from_json(cls, data):
        notice = data.get("notice")
        return cls(
            session_id=str(data["session_id"]),
            state=data.get("state"),
            notice=Notice(*notice) if notice else None,
            project=data.get("project"),
            delay=float(data.get("delay") or 0),
        )


class Check(NamedTuple):
    ok: bool
    text: str


class ConfigError(Exception):
    """The agent's own file is unreadable, so we leave it alone and say so."""


def check(module):
    """Raise TypeError when a module doesn't implement the contract above."""
    missing = [name for name in REQUIRED if not hasattr(module, name)]
    if missing:
        raise TypeError(f"{module.__name__} is not an adapter: missing {', '.join(missing)}")
    if module.SHAPE not in (CONFIG, PLUGIN):
        raise TypeError(f"{module.__name__}.SHAPE must be {CONFIG!r} or {PLUGIN!r}")
    if module.TIER not in (PRO, FREE):
        raise TypeError(f"{module.__name__}.TIER must be {PRO!r} or {FREE!r}")
    return module


def session_id(*candidates):
    """The first usable session id, or "default"."""
    for candidate in candidates:
        if candidate:
            return str(candidate)
    return "default"


def project_of(*candidates):
    """The project name for a notification title: the last path component of the first usable candidate."""
    for candidate in candidates:
        if candidate:
            return os.path.basename(os.path.normpath(str(candidate))) or None
    return None


def summarize(text, length=120):
    """The first non-empty line of `text`, without Markdown markers, shortened to fit a notification."""
    line = next((line for line in str(text or "").splitlines() if line.strip()), "")
    line = " ".join(line.replace("**", "").replace("`", "").lstrip("#>*- \t").split())
    if len(line) > length:
        line = line[: length - 1].rstrip() + "…"
    return line


def home(env_var, default):
    """An agent's config home: the env var it honours, else the default under the user's home."""
    override = os.environ.get(env_var) if env_var else None
    return Path(override) if override else Path.home() / default


def describe(path):
    """A path as the installer prints it: with ~ for the home directory, and forward slashes after it
    on every OS, so the output reads the same as the documentation."""
    text = str(path)
    home_dir = str(Path.home())
    if text.startswith(home_dir):
        return "~" + text[len(home_dir):].replace("\\", "/")
    return text
