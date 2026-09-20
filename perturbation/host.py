"""Chrome native-messaging host: one process for every agent.

It watches the whole sessions tree, pushes a per-agent status to the extension whenever it changes, and
takes a few settings back from the popup (mute, order). Frames are a 4-byte native-endian length prefix
followed by UTF-8 JSON, in both directions.
"""
import json
import os
import struct
import sys
import threading
import time

from . import __version__, agents, config, state

POLL_SECONDS = 0.5


def status(now=None, settings=None):
    """The message the extension renders. Agents arrive in the user's order, so it never sorts."""
    settings = config.load() if settings is None else settings
    watched = set(settings["agents"])
    rows = []
    summaries = []
    for adapter in agents.ordered(settings["order"]):
        summary = state.summary(adapter.ID, now) if adapter.ID in watched else {"state": state.READY, "busy": 0, "waiting": 0, "total": 0}
        if adapter.ID in watched:
            summaries.append(summary)
        rows.append(
            {
                "id": adapter.ID,
                "name": adapter.NAME,
                "short": adapter.SHORT,
                "watched": adapter.ID in watched,
                "muted": bool(settings["mute"].get(adapter.ID)),
                **summary,
            }
        )
    message = {"type": "status", "version": __version__, **state.overall(summaries, settings["count_waiting_as_busy"]), "agents": rows}
    return message


def encode(message):
    data = json.dumps(message).encode("utf-8")
    return struct.pack("@I", len(data)) + data


def _read_exact(stream, size):
    data = b""
    while len(data) < size:
        chunk = stream.read(size - len(data))
        if not chunk:
            return None
        data += chunk
    return data


def read_message(stream):
    """One frame from the extension, or None at end of stream."""
    header = _read_exact(stream, 4)
    if header is None:
        return None
    (length,) = struct.unpack("@I", header)
    body = _read_exact(stream, length)
    if body is None:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError:
        return {}


def handle(message, settings):
    """Apply a settings message from the popup. Returns True when config.json changed."""
    if not isinstance(message, dict):
        return False
    kind = message.get("type")
    if kind == "mute" and isinstance(message.get("id"), str):
        settings["mute"][message["id"]] = bool(message.get("muted"))
        settings["mute"] = {k: v for k, v in settings["mute"].items() if v}
    elif kind == "order" and isinstance(message.get("ids"), list):
        known = agents.ids()
        settings["order"] = [i for i in message["ids"] if isinstance(i, str) and i in known]
    elif kind == "get":
        return True  # nothing to save, but resend the status
    else:
        return False
    config.save(settings)
    return True


class Host:
    def __init__(self, stdin, stdout):
        self.stdin = stdin
        self.stdout = stdout
        self.wake = threading.Event()  # set when a resend is due regardless of change
        self.lock = threading.Lock()

    def reader(self):
        # Chrome closes our stdin when the extension disconnects; anything before that is a settings message.
        while True:
            message = read_message(self.stdin)
            if message is None:
                os._exit(0)
            with self.lock:
                if handle(message, config.load()):
                    self.wake.set()

    def send(self, message):
        self.stdout.write(encode(message))
        self.stdout.flush()

    def run(self):
        threading.Thread(target=self.reader, daemon=True).start()
        last = None
        while True:
            with self.lock:
                current = status()
            if current != last or self.wake.is_set():
                self.wake.clear()
                self.send(current)
                last = current
            time.sleep(POLL_SECONDS)


def main():
    if sys.platform == "win32":
        import msvcrt

        # Text mode would turn \n into \r\n inside the binary frames.
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    Host(sys.stdin.buffer, sys.stdout.buffer).run()
