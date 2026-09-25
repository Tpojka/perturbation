"""Opera. Like Brave it reads Chrome's folder on macOS.

Windows keeps its user data under %APPDATA%, not %LOCALAPPDATA% where the others sit, so it has no
entry there: on Windows it is found by its App Paths registration, and can always be ticked by hand.
"""
from .base import CHROMIUM

ID = "opera"
NAME = "Opera"
ORDER = 4
FAMILY = CHROMIUM
PROFILE = {"darwin": "com.operasoftware.Opera", "linux": "opera"}
APPS = {"darwin": ("Opera.app",), "linux": ("opera", "opera-stable"), "win32": ("opera.exe", "launcher.exe")}
KEY = r"Software\Opera Software\NativeMessagingHosts"
PROCESS = ("Opera.app", "/opera/opera", "opera.exe")  # how this browser looks in a process list, matched case-insensitively
PAGE = "opera://extensions"
