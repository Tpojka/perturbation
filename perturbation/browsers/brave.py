"""Brave. On macOS it also reads Chrome's folder, so it can run on a Chrome install alone; we still
register it in its own folder, which is what keeps it working when Chrome is removed or never there."""
from .base import CHROMIUM

ID = "brave"
NAME = "Brave"
ORDER = 3
FAMILY = CHROMIUM
PROFILE = {"darwin": "BraveSoftware/Brave-Browser", "linux": "BraveSoftware/Brave-Browser", "win32": "BraveSoftware/Brave-Browser/User Data"}
APPS = {"darwin": ("Brave Browser.app",), "linux": ("brave-browser", "brave-browser-stable", "brave"), "win32": ("brave.exe",)}
KEY = r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts"
PAGE = "brave://extensions"
