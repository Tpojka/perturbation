"""Status line handler for agents whose TUI runs a command on every state change and renders its stdout.

Its stdout *is* the status line, so it never prints an error: one short line, always, and exit 0.
"""
import json
import sys

from . import agents, hook, state

LABELS = {state.BUSY: "working", state.WAITING: "needs you", state.READY: "ready"}


def handle(adapter, payload):
    """Record the state the payload describes and return the line to print."""
    result = adapter.statusline(payload)
    if result is None:
        return ""
    update, text = result
    if update is not None:
        hook.apply(adapter, update)
    return render(adapter, update, text)


def render(adapter, update, text):
    """`perturbation · needs you · 1 of 2 sessions working`: this session, then what the agent's own
    line can't know — how its other sessions are doing."""
    line = "perturbation"
    if text:
        line += f" · {text}"
    elif update is not None and update.state in LABELS:
        line += f" · {LABELS[update.state]}"
    summary = state.summary(adapter.ID)
    if summary["total"] > 1:
        line += f" · {summary['busy']} of {summary['total']} sessions working"
    return line


def main(argv=None):
    line = ""
    try:
        argv = sys.argv[2:] if argv is None else argv
        adapter = agents.get(argv[0]) if argv else None
        if adapter is not None and hasattr(adapter, "statusline"):
            # Bytes, because the payload is UTF-8 and Windows would decode text stdin with the ANSI code page.
            payload = json.loads(sys.stdin.buffer.read())
            if isinstance(payload, dict):
                line = handle(adapter, payload)
    except Exception:
        line = ""  # an error here would be rendered as the status line
    # Bytes again: print() would encode the separator with the ANSI code page on Windows and turn the
    # newline into CRLF, and the TUI renders exactly what it gets.
    sys.stdout.buffer.write(line.encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()
