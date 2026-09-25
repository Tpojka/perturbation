"""Chromium itself.

Snap and Flatpak builds are sandboxed and cannot start a native host at all; they keep their profile
elsewhere, so they are not detected here and ticking Chromium will not make them work.
"""
from .base import CHROMIUM

ID = "chromium"
NAME = "Chromium"
ORDER = 7
FAMILY = CHROMIUM
PROFILE = {"darwin": "Chromium", "linux": "chromium", "win32": "Chromium/User Data"}
APPS = {"darwin": ("Chromium.app",), "linux": ("chromium", "chromium-browser"), "win32": ("chromium.exe",)}
KEY = r"Software\Chromium\NativeMessagingHosts"
PAGE = "chrome://extensions"
