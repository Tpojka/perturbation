"""Vivaldi."""
from .base import CHROMIUM

ID = "vivaldi"
NAME = "Vivaldi"
ORDER = 5
FAMILY = CHROMIUM
PROFILE = {"darwin": "Vivaldi", "linux": "vivaldi", "win32": "Vivaldi/User Data"}
APPS = {"darwin": ("Vivaldi.app",), "linux": ("vivaldi", "vivaldi-stable"), "win32": ("vivaldi.exe",)}
KEY = r"Software\Vivaldi\NativeMessagingHosts"
PROCESS = ("Vivaldi",)  # how this browser looks in a process list, matched case-insensitively
PAGE = "vivaldi://extensions"
