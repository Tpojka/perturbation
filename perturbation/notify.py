"""Desktop notifications with tools each OS already has: osascript, notify-send, PowerShell toasts."""
import os
import shutil
import subprocess
import sys

from . import NAME

_QUIET = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}


def send(title, message, icon, sound=True):
    """Show a notification without waiting for it, so the hook returns immediately."""
    if sys.platform == "darwin":
        _macos(title, message, sound)
    elif sys.platform == "win32":
        _windows(title, message, icon, sound)
    else:
        _linux(title, message, icon, sound)


def setup_hint():
    """What the user may need to do before notifications appear, or None."""
    if sys.platform == "darwin":
        return "If none appear, allow notifications for Script Editor in System Settings → Notifications."
    if sys.platform == "win32":
        return "If none appear, check Settings → System → Notifications and Focus assist."
    if not shutil.which("notify-send"):
        return "notify-send not found. Install it with: sudo apt install libnotify-bin"
    return None


def _macos(title, message, sound):
    # Values are passed as arguments, so quotes in a message can't break the script.
    display = f'display notification (item 2 of argv) with title "{NAME}" subtitle (item 1 of argv)'
    if sound:
        display += ' sound name "Glass"'
    script = ["on run argv", display, "end run"]
    args = ["osascript"]
    for line in script:
        args += ["-e", line]
    subprocess.Popen(args + [title, message], **_QUIET)


LINUX_SOUND = "/usr/share/sounds/freedesktop/stereo/complete.oga"


def _linux(title, message, icon, sound):
    command = ["notify-send", "-a", NAME, "-i", str(icon)]
    if not sound:
        command.append("--hint=boolean:suppress-sound:true")  # some desktops add their own sound
    subprocess.Popen(command + [title, message], start_new_session=True, **_QUIET)
    if sound and shutil.which("paplay"):
        subprocess.Popen(["paplay", LINUX_SOUND], start_new_session=True, **_QUIET)


# Registered app ID of Windows PowerShell; lets an unpackaged script raise toasts.
WINDOWS_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"

# Values arrive via environment variables and are XML-escaped, so a message can't inject markup.
# PERTURBATION_AUDIO is one of the two constants below, never user text.
WINDOWS_SCRIPT = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$t = [Security.SecurityElement]::Escape($env:PERTURBATION_TITLE)
$m = [Security.SecurityElement]::Escape($env:PERTURBATION_MESSAGE)
$i = [Security.SecurityElement]::Escape($env:PERTURBATION_ICON)
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$t</text><text>$m</text><image placement='appLogoOverride' src='$i'/></binding></visual>$($env:PERTURBATION_AUDIO)</toast>")
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:PERTURBATION_APP_ID).Show($toast)
"""

WINDOWS_SOUND = "<audio src='ms-winsoundevent:Notification.Default'/>"
WINDOWS_SILENT = "<audio silent='true'/>"  # without it, Windows plays its default sound

CREATE_NO_WINDOW = 0x08000000


def _windows(title, message, icon, sound):
    env = dict(
        os.environ,
        PERTURBATION_TITLE=title,
        PERTURBATION_MESSAGE=message,
        PERTURBATION_ICON=icon.as_uri(),
        PERTURBATION_APP_ID=WINDOWS_APP_ID,
        PERTURBATION_AUDIO=WINDOWS_SOUND if sound else WINDOWS_SILENT,
    )
    command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", WINDOWS_SCRIPT]
    subprocess.Popen(command, env=env, creationflags=CREATE_NO_WINDOW, **_QUIET)
