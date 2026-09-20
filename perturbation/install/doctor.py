"""`python3 -m perturbation.install doctor`: is everything wired up, per agent?"""
import json
import subprocess
import sys

from .. import EXTENSION_ID, __version__, agents, config, paths
from ..agents.base import Check, describe
from . import system


def checks():
    """(section, [Check]) pairs. Sections are the app, Chrome, then one per watched agent."""
    settings = config.load()
    app = paths.app_file()
    commands = system.Commands(app)
    result = [("Perturbation", _app_checks(app)), ("Chrome", _chrome_checks())]
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
    manifest = paths.extension_dir() / "manifest.json"
    result.append(Check(manifest.is_file(), f"extension files {'present' if manifest.is_file() else 'missing'} in {describe(paths.extension_dir())}"))
    if manifest.is_file():
        try:
            version = json.loads(manifest.read_text(encoding="utf-8")).get("version")
            result.append(Check(version == __version__, f"extension files are {version}" + ("" if version == __version__ else "; run the installer again and reload the extension")))
        except (OSError, ValueError):
            result.append(Check(False, "extension manifest is unreadable"))
    return result


def _chrome_checks():
    manifests = system.registered_manifests()
    if not manifests:
        return [Check(False, "native host is not registered with Chrome; run the installer")]
    result = []
    for path in manifests:
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            result.append(Check(False, f"{describe(path)} is unreadable"))
            continue
        result.append(Check(True, f"native host registered in {describe(path)}"))
        launcher = manifest.get("path", "")
        exists = bool(launcher) and __import__("os").path.isfile(launcher)
        result.append(Check(exists, f"host launcher {describe(launcher)} {'exists' if exists else 'is missing'}"))
        origin = f"chrome-extension://{EXTENSION_ID}/"
        result.append(Check(origin in manifest.get("allowed_origins", []), f"manifest allows extension {EXTENSION_ID}"))
    return result


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
