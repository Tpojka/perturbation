"""Arc. macOS only here: its user data sits one level deeper than the others, and the Windows build's
layout is untested, so it is simply not offered there."""
from .base import CHROMIUM

ID = "arc"
NAME = "Arc"
ORDER = 6
FAMILY = CHROMIUM
PROFILE = {"darwin": "Arc/User Data"}
APPS = {"darwin": ("Arc.app",)}
KEY = None
PAGE = "arc://extensions"
