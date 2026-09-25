"""Microsoft Edge. Chromium with its own folder and registry key on every OS it ships for."""
from .base import CHROMIUM

ID = "edge"
NAME = "Microsoft Edge"
ORDER = 2
FAMILY = CHROMIUM
PROFILE = {"darwin": "Microsoft Edge", "linux": "microsoft-edge", "win32": "Microsoft/Edge/User Data"}
APPS = {"darwin": ("Microsoft Edge.app",), "linux": ("microsoft-edge", "microsoft-edge-stable"), "win32": ("msedge.exe",)}
KEY = r"Software\Microsoft\Edge\NativeMessagingHosts"
PAGE = "edge://extensions"
