"""The browser contract. Every browser is one module in this package, and nothing else in the codebase
knows a browser exists.

A module is a browser adapter when it has these attributes (checked by the registry on import):

    ID      = "brave"            config key, argv token, what `set browsers` accepts
    NAME    = "Brave"            shown in the installer, status and doctor
    ORDER   = 3                  position in the installer's list
    FAMILY  = CHROMIUM           which native-messaging dialect it speaks
    PROFILE = {...}              its user-data directory under root(), per platform; a platform that
                                 is missing from the mapping has no build of this browser
    APPS    = {...}              what detect() looks for: a bundle in /Applications on macOS, a
                                 command on PATH on Linux, an App Paths entry on Windows
    PROCESS = (...)              substrings that identify the browser in a process list, on any OS.
                                 They are not the APPS names: a Linux Chrome runs as
                                 /opt/google/chrome/chrome, never as google-chrome
    KEY     = r"Software\\..."    the Windows registry key that holds native hosts, or None
    PAGE    = "brave://extensions"   where the user loads the unpacked extension

Registration is one file per browser: every Chromium browser reads
`<its user data>/NativeMessagingHosts/<host>.json` on macOS and Linux. Windows looks hosts up in the
registry instead, so there a single manifest lives in our data directory and each browser gets its own
key pointing at it.

Some browsers also read another browser's folder - Brave and Opera on macOS both read Chrome's - so a
browser can work without a file of its own. We still write one per browser: that fallback is
undocumented, differs per platform, and leans on a folder belonging to a browser the user may not have.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .. import HOST_NAME, paths
from ..agents.base import describe

CHROMIUM = "chromium"

REQUIRED = ("ID", "NAME", "ORDER", "FAMILY", "PROFILE", "APPS", "PROCESS", "KEY", "PAGE")

HOSTS_DIR = "NativeMessagingHosts"


def check(module):
    """Raise TypeError when a module doesn't implement the contract above."""
    missing = [name for name in REQUIRED if not hasattr(module, name)]
    if missing:
        raise TypeError(f"{module.__name__} is not a browser: missing {', '.join(missing)}")
    if module.FAMILY != CHROMIUM:
        raise TypeError(f"{module.__name__}.FAMILY must be {CHROMIUM!r}")
    return module


def root():
    """Where browsers keep their user data on this OS."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def app_dirs():
    """Where macOS keeps applications. A function so tests can point it somewhere harmless."""
    return [Path("/Applications"), Path.home() / "Applications"]


def profile_dir(module):
    """This browser's user-data directory, or None when it has no build for this OS."""
    name = module.PROFILE.get(sys.platform)
    return root().joinpath(*name.split("/")) if name else None


def supported(module):
    """True when this browser can be registered on this OS at all.

    Windows registers hosts in the registry, so its key is what counts there; everywhere else it is the
    user-data directory whose NativeMessagingHosts folder we write into.
    """
    if sys.platform == "win32":
        return bool(module.KEY)
    return profile_dir(module) is not None


def host_dir(module):
    """The folder this browser reads native-host manifests from (macOS and Linux only)."""
    profile = profile_dir(module)
    if profile is None or sys.platform == "win32":
        return None
    return profile / HOSTS_DIR


def app(module):
    """Where the browser itself is, or None. Detection proper, not a leftover profile."""
    names = module.APPS.get(sys.platform, ())
    if sys.platform == "darwin":
        for name in names:
            for directory in app_dirs():
                if (directory / name).exists():
                    return directory / name
        return None
    if sys.platform == "win32":
        return _windows_app(names)
    for name in names:
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def _windows_app(names):
    import winreg

    for name in names:
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive, rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{name}") as key:
                    value, _ = winreg.QueryValueEx(key, "")
            except OSError:
                continue
            if value and Path(value).is_file():
                return Path(value)
    return None


def detect(module):
    """A short note on where this browser was found, or None.

    A profile without the application is reported as such: folders outlive uninstalls, so a profile
    alone is a hint for the menu, never proof the browser is there.
    """
    if not supported(module):
        return None
    found = app(module)
    if found:
        return describe(found)
    profile = profile_dir(module)
    if profile is not None and profile.is_dir():
        return f"{describe(profile)} (profile only)"
    return None


def shared_manifest(host_name=HOST_NAME, data_dir=None):
    """The one manifest file on Windows, which every browser's registry key points at."""
    return (data_dir or paths.data_dir()) / f"{host_name}.json"


def manifest_file(module, host_name=HOST_NAME):
    """Where this browser's manifest goes, whether or not it is there yet."""
    if not supported(module):
        return None
    if sys.platform == "win32":
        return shared_manifest(host_name)
    return host_dir(module) / f"{host_name}.json"


def key_path(module, host_name=HOST_NAME):
    return rf"{module.KEY}\{host_name}" if module.KEY else None


def location(module, host_name=HOST_NAME):
    """What the installer prints: the file it wrote, or the registry key it set."""
    if not supported(module):
        return None
    if sys.platform == "win32":
        return rf"HKCU\{key_path(module, host_name)}"
    return describe(manifest_file(module, host_name))


def register(module, manifest, host_name=HOST_NAME):
    """Write our manifest for this browser. Returns what to print, or None when it can't be registered."""
    if not supported(module):
        return None
    text = json.dumps(manifest, indent=2) + "\n"
    target = manifest_file(module, host_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    if sys.platform == "win32":
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path(module, host_name)) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(target))
    return location(module, host_name)


def registered(module, host_name=HOST_NAME):
    """The manifest this browser would read, when it is actually there. Else None."""
    if not supported(module):
        return None
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path(module, host_name)) as key:
                value, _ = winreg.QueryValueEx(key, "")
        except OSError:
            return None
        return Path(value) if value else None
    target = manifest_file(module, host_name)
    return target if target.is_file() else None


def unregister(module, host_name=HOST_NAME):
    """Remove our registration for this browser. Returns what was removed, for printing."""
    if not supported(module):
        return []
    removed = []
    if sys.platform == "win32":
        import winreg

        if registered(module, host_name) is not None:
            removed.append(location(module, host_name))
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path(module, host_name))
        except OSError:
            pass
        return removed
    target = manifest_file(module, host_name)
    try:
        target.unlink()
        removed.append(describe(target))
    except OSError:
        pass
    return removed


def owner(command):
    """The browser whose process command line this is, or None.

    Every browser's PROCESS patterns are tried, whatever the OS, and the longest match wins, so a path
    fragment beats a bare name and "Google Chrome" is never taken for Chromium.
    """
    from . import known

    text = command.lower()
    best = None
    for module in known():
        for pattern in module.PROCESS:
            needle = pattern.lower()
            if needle in text and (best is None or len(needle) > len(best[1])):
                best = (module, needle)
    return best[0] if best else None


def running_hosts(app_name="perturbation.pyz"):
    """[(browser or None, pid)] for the host processes browsers have started.

    A manifest in a folder proves a registration; a running host proves a browser is actually using it,
    which is the only check that survives browsers reading each other's folders. macOS and Linux only.
    """
    if sys.platform == "win32":
        return []
    try:
        out = subprocess.run(["ps", "-Ao", "pid=,ppid=,command="], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    processes = {}
    for line in out.decode("utf-8", "replace").splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3:
            processes[parts[0]] = (parts[1], parts[2])
    found = []
    for pid, (parent, command) in processes.items():
        if f"{app_name} host" in command and "ps -Ao" not in command:
            found.append((owner(processes.get(parent, ("", ""))[1]), int(pid)))
    return found
