"""`python3 -m perturbation.install doctor`: is everything wired up, per agent?"""
import json
import subprocess
import sys
from pathlib import Path

from .. import EXTENSION_ID, __version__, agents, browsers, config, paths
from ..agents.base import Check, describe
from . import system


def checks():
    """(section, [Check]) pairs. Sections are the app, the browsers, then one per watched agent."""
    settings = config.load()
    app = paths.app_file()
    commands = system.Commands(app)
    result = [("Perturbation", _app_checks(app)), ("Browsers", _browser_checks(settings))]
    if not settings["agents"]:
        result.append(("Agents", [Check(False, "no agents are watched; run the installer or `set agents`")]))
    for adapter in agents.ordered(settings["order"]):
        if adapter.ID not in settings["agents"]:
            continue
        try:
            agent_checks = adapter.doctor(commands.for_agent(adapter.ID))
        except Exception as error:  # a broken adapter must not hide the other results
            agent_checks = [Check(False, f"doctor failed: {error}")]
        result.append((adapter.NAME, agent_checks))
    return result


def _app_checks(app):
    result = [Check(app.is_file(), f"{describe(app)} {'is installed' if app.is_file() else 'is missing; run the installer'}")]
    if app.is_file():
        try:
            version = subprocess.run([sys.executable, str(app), "version"], capture_output=True, text=True, timeout=30).stdout.strip()
        except (OSError, subprocess.SubprocessError) as error:
            version = ""
            result.append(Check(False, f"the installed app doesn't run: {error}"))
        if version:
            result.append(Check(version == __version__, f"installed app is {version}" + ("" if version == __version__ else f", this repository is {__version__}; run the installer again")))
    if config.damaged():
        result.append(Check(False, f"{describe(paths.config_file())} can't be read, so the defaults are in use; run the installer to write it again"))
    manifest = paths.extension_dir() / "manifest.json"
    result.append(Check(manifest.is_file(), f"extension files {'present' if manifest.is_file() else 'missing'} in {describe(paths.extension_dir())}"))
    if manifest.is_file():
        try:
            version = json.loads(manifest.read_text(encoding="utf-8")).get("version")
            result.append(Check(version == __version__, f"extension files are {version}" + ("" if version == __version__ else "; run the installer again and reload the extension")))
        except (OSError, ValueError):
            result.append(Check(False, "extension manifest is unreadable"))
    return result


def _browser_checks(settings):
    """One line per browser we should be registered with, plus what is actually running.

    A browser without a manifest of its own is not necessarily broken - Brave and Opera read Chrome's
    folder on macOS - so a missing file is reported against what we were asked to register, and the
    running hosts are reported separately as the only proof a browser is really attached.
    """
    chosen = settings["browsers"] or [b.ID for b, _ in system.registrations()]
    if not chosen:
        return [Check(False, "no browser is registered; run the installer or `set browsers`")]
    result = []
    for module in browsers.some(chosen):
        if not browsers.base.supported(module):
            result.append(Check(False, f"{module.NAME}: no build of it can be registered on {system.label()}"))
            continue
        manifest_path = browsers.base.registered(module)
        if manifest_path is None:
            result.append(Check(False, f"{module.NAME}: not registered; run the installer again"))
            continue
        result.append(Check(True, f"{module.NAME}: registered in {browsers.base.location(module)}"))
        result += _manifest_checks(module, manifest_path)
    for module, path in system.registrations():
        if module.ID not in chosen:
            result.append(Check(False, f"{module.NAME}: left-over registration in {describe(path)}; run `set browsers` to clear it"))
    result.append(_running_check())
    return result


def _manifest_checks(module, path):
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [Check(False, f"{module.NAME}: {describe(path)} is unreadable")]
    launcher = manifest.get("path", "")
    exists = bool(launcher) and Path(launcher).is_file()
    origin = f"chrome-extension://{EXTENSION_ID}/"
    return [
        Check(exists, f"{module.NAME}: host launcher {describe(launcher)} {'exists' if exists else 'is missing'}"),
        Check(origin in manifest.get("allowed_origins", []), f"{module.NAME}: manifest allows extension {EXTENSION_ID}"),
    ]


def _running_check():
    """Informational: which browsers have actually started a host. Never a failure - a closed browser
    has no host running, and Windows isn't asked at all."""
    running = browsers.base.running_hosts(paths.app_file().name)
    if not running:
        return Check(True, "no host is running (no browser has the extension open, or this is Windows)")
    names = sorted({module.NAME if module else "unknown browser" for module, _ in running})
    return Check(True, f"{len(running)} host{'s' if len(running) != 1 else ''} running: {', '.join(names)}")


def run():
    """Print every check and return the exit code."""
    failed = 0
    for section, section_checks in checks():
        print(f"\n{section}")
        for check in section_checks:
            print(f"  {'✓' if check.ok else '✗'} {check.text}")
            failed += not check.ok
    print()
    print("All good." if not failed else f"{failed} problem{'s' if failed != 1 else ''} found.")
    return 1 if failed else 0
