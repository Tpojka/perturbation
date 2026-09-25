"""OS-specific install steps: how hooks start Python, and how browsers find the native host."""
import shlex
import sys
from pathlib import Path

from .. import EXTENSION_ID, HOST_NAME, NAME, browsers, paths
from ..browsers import base

LABELS = {"darwin": "macOS", "linux": "Ubuntu/Linux", "win32": "Windows"}


def label():
    return LABELS.get(sys.platform, sys.platform)


def _powershell_quote(text):
    return "'" + text.replace("'", "''") + "'"


class Commands:
    """The shell commands written into agents' hook files, for one installed app.

    Every hook command is hardened to exit 0 and print nothing, even when Python or the app is missing:
    Copilot denies a tool call when a preToolUse hook fails, Claude's PreCompact exit 2 blocks
    compaction, Antigravity parses stdout as a decision and its exit codes are undocumented. Python
    itself exits 2 when it can't find the app, which is exactly what `|| true` and `; exit 0` absorb.
    """

    def __init__(self, app):
        self.app = Path(app)
        # On Windows `python` may be the Microsoft Store stub, so hooks name this interpreter's path.
        self.python = sys.executable if sys.platform == "win32" else "python3"
        self.shell = "powershell" if sys.platform == "win32" else "bash"

    def _base(self, shell, *args):
        if shell == "powershell":
            return " ".join(["&", _powershell_quote(self.python), _powershell_quote(str(self.app))] + list(args))
        if sys.platform == "win32":
            # A POSIX shell on Windows (Git Bash, which Goose uses): forward slashes and this interpreter.
            python, app = Path(sys.executable).as_posix(), self.app.as_posix()
        else:
            python, app = self.python, str(self.app)
        return " ".join([shlex.quote(python), shlex.quote(app)] + list(args))

    def hook(self, agent_id, event=None, shell=None):
        """`shell` is "sh" for agents that run every hook through `sh -c` whatever the OS."""
        shell = shell or self.shell
        args = ["hook", agent_id] + ([event] if event else [])
        return self._base(shell, *args) + ("; exit 0" if shell == "powershell" else " || true")

    def statusline(self, agent_id, shell=None):
        # Its stdout *is* the status line, so no `|| true`: the script prints one line and swallows errors.
        return self._base(shell or self.shell, "statusline", agent_id)

    def for_agent(self, agent_id):
        return AgentCommands(self, agent_id)


class AgentCommands:
    """What an adapter's install() receives: the commands, already bound to its agent."""

    def __init__(self, commands, agent_id):
        self._commands = commands
        self.agent_id = agent_id
        self.app = commands.app
        self.python = commands.python if sys.platform == "win32" else "python3"
        self.shell = commands.shell

    def hook(self, event=None, shell=None):
        return self._commands.hook(self.agent_id, event, shell)

    def statusline(self, shell=None):
        return self._commands.statusline(self.agent_id, shell)


def write_host_launcher(app):
    """Chrome starts native hosts as executables, so wrap `python perturbation.pyz host` in a script."""
    if sys.platform == "win32":
        launcher = paths.data_dir() / "perturbation-host.bat"
        with open(launcher, "w", newline="\r\n") as f:
            f.write(f'@echo off\n"{sys.executable}" "{app}" host %*\n')
    else:
        launcher = paths.data_dir() / "perturbation-host"
        launcher.write_text(f'#!/bin/sh\nexec python3 {shlex.quote(str(app))} host "$@"\n')
        launcher.chmod(0o755)
    return launcher


def host_manifest(launcher, host_name=HOST_NAME, extension_id=EXTENSION_ID):
    return {
        "name": host_name,
        "description": f"{NAME}: coding agent status in the browser",
        "path": str(launcher),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id}/"],
    }


def register_host(launcher, browser_ids=None, host_name=HOST_NAME):
    """Tell the chosen browsers where the native host is. Returns [(browser, where)], for printing.

    One registration per browser, never a shared one: some Chromium browsers also read Chrome's folder,
    but that is undocumented, differs per platform, and leans on a browser the user may not have.
    """
    manifest = host_manifest(launcher, host_name)
    chosen = browsers.some(browser_ids) if browser_ids is not None else [browsers.get(browsers.DEFAULT)]
    written = []
    for browser in chosen:
        where = base.register(browser, manifest, host_name)
        if where:
            written.append((browser, where))
    return written


def registrations(host_name=HOST_NAME):
    """[(browser, manifest path)] for every browser that has this host registered."""
    found = []
    for browser in browsers.known():
        path = base.registered(browser, host_name)
        if path is not None:
            found.append((browser, path))
    return found


def registered_manifests(host_name=HOST_NAME):
    """Every manifest registered for `host_name`, whichever browser reads it."""
    return [path for _, path in registrations(host_name)]


def unregister_host(host_name=HOST_NAME, browser_ids=None):
    """Remove the registration from every browser, or only from the named ones. Returns what went."""
    chosen = browsers.some(browser_ids) if browser_ids is not None else browsers.known()
    removed = []
    for browser in chosen:
        removed += base.unregister(browser, host_name)
    if sys.platform == "win32" and not registrations(host_name):
        # The manifest itself is shared on Windows: it goes when the last key pointing at it does.
        try:
            base.shared_manifest(host_name).unlink()
        except OSError:
            pass
    return removed
