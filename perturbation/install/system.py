"""OS-specific install steps: how hooks start Python, and how Chrome finds the native host."""
import json
import os
import shlex
import sys
from pathlib import Path

from .. import EXTENSION_ID, HOST_NAME, NAME, paths

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
        "description": f"{NAME}: coding agent status for Chrome",
        "path": str(launcher),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id}/"],
    }


def register_host(launcher):
    """Tell Chrome where the native host is. Returns the manifest paths written."""
    manifest = json.dumps(host_manifest(launcher), indent=2) + "\n"
    if sys.platform == "win32":
        import winreg

        target = manifest_path()
        target.write_text(manifest)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, windows_key(HOST_NAME)) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(target))
        return [target]

    written = []
    for directory in manifest_dirs():
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{HOST_NAME}.json"
        target.write_text(manifest)
        written.append(target)
    return written


def manifest_path(host_name=HOST_NAME, data_dir=None):
    """The native host manifest Chrome reads (the Chrome one, on Linux)."""
    if sys.platform == "win32":
        return (data_dir or paths.data_dir()) / f"{host_name}.json"
    return manifest_dirs()[0] / f"{host_name}.json"


def registered_manifests(host_name=HOST_NAME, data_dir=None):
    """Every manifest registered for `host_name`, on this OS."""
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, windows_key(host_name)) as key:
                value, _ = winreg.QueryValueEx(key, "")
        except OSError:
            return []
        return [Path(value)]
    return [d / f"{host_name}.json" for d in manifest_dirs(all_browsers=True) if (d / f"{host_name}.json").is_file()]


def unregister_host(host_name=HOST_NAME):
    if sys.platform == "win32":
        import winreg

        for manifest in registered_manifests(host_name):
            try:
                manifest.unlink()
            except OSError:
                pass
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, windows_key(host_name))
        except FileNotFoundError:
            pass
        return
    for directory in manifest_dirs(all_browsers=True):
        try:
            (directory / f"{host_name}.json").unlink()
        except FileNotFoundError:
            pass


def windows_key(host_name):
    return rf"Software\Google\Chrome\NativeMessagingHosts\{host_name}"


def manifest_dirs(all_browsers=False):
    if sys.platform == "darwin":
        return [Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "NativeMessagingHosts"]
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    # Chrome always; Chromium only when it has a profile (Snap/Flatpak browsers can't start native hosts).
    browsers = ["google-chrome", "chromium"]
    return [
        config / b / "NativeMessagingHosts"
        for b in browsers
        if all_browsers or b == "google-chrome" or (config / b).is_dir()
    ]
