"""The installer's questions: which agents to watch, which browsers to register, what to install, yes/no.

The agent and browser questions share one picker. Number keys toggle a row directly, ↑/↓ (or j/k) move
a cursor and Space toggles the row under it, Enter confirms. All seven agents are listed alike, the
free-tier ones after the pro-tier ones; folding the free tier behind a "more" row is still supported
(`fold_free=True`) but off by default. When stdin isn't a terminal, the same picker reads whole lines
instead, so it works in pipes and tests.

The picker knows nothing about what it lists: any adapter with ID, NAME and a place in a registry does.
"""
import os
import sys

from .. import __version__
from ..agents.base import FREE
from . import system

MENU = """
Perturbation {version} installer ({os})

What should be installed?
  1) Browser extension
  2) Browser extension + OS notifier
  3) Nothing (exit)
"""

CONFIRM, CANCEL = "confirm", "cancel"
MORE = object()  # the folded row


class Picker:
    """The picker's state: which rows are checked, where the cursor is, whether the free tier is shown."""

    def __init__(self, adapters, selected, detected, fold_free=False):
        self.adapters = list(adapters)
        self.selected = set(selected)
        self.detected = detected
        self.folded = [a for a in self.adapters if a.TIER == FREE] if fold_free else []
        # A free-tier agent that is on the machine, or already watched, is never hidden.
        self.expanded = not self.folded or any(a.ID in self.selected or detected.get(a.ID) for a in self.folded)
        self.cursor = 0

    def visible(self):
        if self.expanded:
            return list(self.adapters)
        return [a for a in self.adapters if a not in self.folded] + [MORE]

    def numbers(self):
        """The number keys that toggle something right now."""
        return len(self.adapters) if self.expanded else len(self.adapters) - len(self.folded)

    def lines(self, cursor=True):
        rows = []
        for index, row in enumerate(self.visible()):
            pointer = ">" if cursor and index == self.cursor else " "
            if row is MORE:
                names = ", ".join(a.NAME for a in self.folded)
                rows.append(f"{pointer}     +) {len(self.folded)} more, free tier: {names}")
            else:
                mark = "x" if row.ID in self.selected else " "
                rows.append(f"{pointer} [{mark}] {self.adapters.index(row) + 1}) {row.NAME:<22} {self.detected.get(row.ID) or 'not found'}")
        return rows

    def prompt(self, keys=True):
        more = "" if self.expanded else ", + shows more"
        if keys:
            return f"Space or 1-{self.numbers()} toggles, ↑/↓ moves, a: all, n: none{more}, Enter confirms: "
        return f"Toggle with 1-{self.numbers()} (a: all, n: none{more}), Enter to confirm: "

    def key(self, key):
        """Apply one key. Returns CONFIRM, CANCEL or None."""
        if key in ("enter",):
            return CONFIRM
        if key in ("esc", "cancel", "q"):
            return CANCEL
        if key.isdigit() and 1 <= int(key) <= len(self.adapters):
            adapter = self.adapters[int(key) - 1]
            if adapter in self.folded and not self.expanded:
                self.expand()
            self.selected ^= {adapter.ID}
        elif key == "space":
            row = self.visible()[self.cursor]
            if row is MORE:
                self.expand()
            else:
                self.selected ^= {row.ID}
        elif key in ("up", "k"):
            self.cursor = max(0, self.cursor - 1)
        elif key in ("down", "j"):
            self.cursor = min(len(self.visible()) - 1, self.cursor + 1)
        elif key in ("+", "m"):
            self.expand()
        elif key == "a":
            self.selected = {a.ID for a in self.visible() if a is not MORE}
        elif key == "n":
            self.selected = set()
        return None

    def expand(self):
        self.expanded = True
        self.cursor = min(self.cursor, len(self.visible()) - 1)

    def result(self):
        return [a.ID for a in self.adapters if a.ID in self.selected]


def choose(question, adapters, selected, detected, fold_free=False):
    """Ask one picker question. Returns the chosen ids in registry order, or None when the user backs out."""
    picker = Picker(adapters, selected, detected, fold_free)
    print()
    print(question)
    if interactive():
        return _pick_with_keys(picker)
    return _pick_with_lines(picker)


def choose_agents(adapters, selected, detected, fold_free=False):
    return choose("Which agents should be watched?", adapters, selected, detected, fold_free)


def choose_browsers(adapters, selected, detected):
    """Which browsers get the native host registered. The extension itself is still loaded by hand."""
    return choose("Which browsers should the lamp work in?", adapters, selected, detected)


def interactive():
    """True when keys can be read one at a time: a real terminal on both ends."""
    try:
        return sys.stdin.isatty() and sys.stdout.isatty() and os.environ.get("TERM") != "dumb" and not os.environ.get("PERTURBATION_PLAIN_MENU")
    except (AttributeError, ValueError):
        return False


def _pick_with_keys(menu):
    drawn = 0
    while True:
        if drawn:
            sys.stdout.write(f"\x1b[{drawn}A\x1b[J")  # back up over the last drawing and clear it
        lines = menu.lines() + [menu.prompt()]
        sys.stdout.write("\n".join(lines))
        sys.stdout.flush()
        try:
            action = menu.key(read_key())
        except (KeyboardInterrupt, EOFError):
            action = CANCEL
        drawn = len(lines) - 1
        if action:
            print()
            return menu.result() if action == CONFIRM else None


def _pick_with_lines(menu):
    while True:
        print("\n".join(menu.lines(cursor=False)))
        try:
            answer = input(menu.prompt(keys=False)).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not answer:
            return menu.result()
        for token in answer.replace(",", " ").split():
            if menu.key({"+": "+", "m": "+"}.get(token, token)) == CANCEL:
                return None


def read_key():
    """One key from the terminal: a character, or "up", "down", "enter", "space", "esc", "cancel"."""
    if sys.platform == "win32":
        import msvcrt

        char = msvcrt.getwch()
        if char in ("\x00", "\xe0"):  # an arrow or function key: a second code follows
            return {"H": "up", "P": "down"}.get(msvcrt.getwch(), "")
        return _normalize(char)

    import select
    import termios
    import tty

    # The raw descriptor, not sys.stdin: its buffer would swallow the rest of an arrow key's escape
    # sequence, and a bare ESC would then read as a cancel.
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)  # keeps Ctrl+C as SIGINT, so it still cancels
        char = os.read(fd, 1)
        if not char:
            raise EOFError
        if char == b"\x1b":
            sequence = b""
            while len(sequence) < 2 and select.select([fd], [], [], 0.05)[0]:
                sequence += os.read(fd, 1)
            if sequence == b"[A":
                return "up"
            if sequence == b"[B":
                return "down"
            return "esc"
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
    return _normalize(char.decode("utf-8", "ignore"))


def _normalize(char):
    return {"\r": "enter", "\n": "enter", " ": "space", "\x03": "cancel", "\x04": "cancel", "\x1b": "esc"}.get(char, char.lower())


def choose_install():
    print(MENU.format(version=__version__, os=system.label()))
    while True:
        try:
            choice = input("Choose 1, 2 or 3: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return "3"
        if choice in ("1", "2", "3"):
            return choice


def ask_yes_no(question, default=True):
    prompt = "[Y/n]" if default else "[y/N]"
    while True:
        try:
            answer = input(f"{question} {prompt}: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return default
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
