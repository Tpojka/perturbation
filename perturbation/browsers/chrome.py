"""Google Chrome. The folder other Chromium browsers fall back to, which is why it is listed first."""
from .base import CHROMIUM

ID = "chrome"
NAME = "Google Chrome"
ORDER = 1
FAMILY = CHROMIUM
PROFILE = {"darwin": "Google/Chrome", "linux": "google-chrome", "win32": "Google/Chrome/User Data"}
APPS = {"darwin": ("Google Chrome.app",), "linux": ("google-chrome", "google-chrome-stable"), "win32": ("chrome.exe",)}
KEY = r"Software\Google\Chrome\NativeMessagingHosts"
PAGE = "chrome://extensions"
