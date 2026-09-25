# Adding a browser

Every browser is one module in `perturbation/browsers/`. Nothing else in the codebase knows a browser exists: the installer, the status command and the doctor all go through the registry and the contract in `perturbation/browsers/base.py`.

A browser module is data, not behaviour — where that browser keeps its user data, how to recognise it, and where it looks up native messaging hosts.

## 1. Write the module

```python
ID      = "brave"            # config key, argv token, what `set browsers` accepts
NAME    = "Brave"            # shown in the installer, status and doctor
ORDER   = 3                  # position in the installer's list
FAMILY  = CHROMIUM           # the native-messaging dialect it speaks
PROFILE = {"darwin": "BraveSoftware/Brave-Browser", "linux": "BraveSoftware/Brave-Browser", "win32": "BraveSoftware/Brave-Browser/User Data"}
APPS    = {"darwin": ("Brave Browser.app",), "linux": ("brave-browser", "brave"), "win32": ("brave.exe",)}
KEY     = r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts"
PAGE    = "brave://extensions"
```

- `PROFILE` is relative to `base.root()`: `~/Library/Application Support` on macOS, `$XDG_CONFIG_HOME` (or `~/.config`) on Linux, `%LOCALAPPDATA%` on Windows. Leave a platform out when the browser has no build for it, or when it keeps its data somewhere else entirely — Opera on Windows does, and is then found by `APPS` alone.
- The manifest folder is always `<PROFILE>/NativeMessagingHosts` on macOS and Linux. There is no per-browser exception; Arc's extra `User Data` level lives in its `PROFILE`.
- `KEY` is the Windows registry key under `HKEY_CURRENT_USER`, where the manifest is one shared file in our data directory and each browser gets a value pointing at it. `None` means the browser can't be registered on Windows.
- `APPS` is how `detect()` finds the browser itself: a bundle under `/Applications` on macOS, a command on `PATH` on Linux, an `App Paths` registry entry on Windows. A profile folder alone is reported as `(profile only)` and left unchecked, because folders outlive uninstalls.

## 2. Register it

Add the module name to `MODULES` in `perturbation/browsers/__init__.py`. The registry checks the contract on import and sorts by `ORDER`.

## 3. Test it

`tests/test_browsers.py` runs every registered browser through the contract. Add a case there when the browser needs one of its own — an unusual path, or a platform it skips.

Verify the paths on a real machine, not from documentation: register the host, load the extension, and check that a host process appears with that browser as its parent (`python3 -m perturbation.install status` prints which browsers are running one). Vendors patch native messaging — Brave and Opera also read Chrome's folder on macOS — so a browser that works is not proof that its own path is right. The one that isn't read is dead weight, and only a live check finds it.

## 4. Document it

Add the browser to the table in `README.md`, to the requirements line on `site/index.md` and `site/index.html`, and to `CHANGELOG.md`.

## Firefox

Firefox is not in this list, and it is not one module away. It uses `allowed_extensions` with a `gecko` id instead of `allowed_origins`, keeps its manifests somewhere else, needs an event page rather than a service worker, and — unlike Chrome — refuses to keep an unsigned extension, which makes AMO signing part of every release. `FAMILY` exists so that work has somewhere to land.
