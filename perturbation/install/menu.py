"""The installer's questions: which agents to watch, what to install, and yes/no."""
from .. import __version__
from . import system

MENU = """
Perturbation {version} installer ({os})

What should be installed?
  1) Chrome extension
  2) Chrome extension + OS notifier
  3) Nothing (exit)
"""


def choose_agents(adapters, selected, detected):
    """Ask which agents to watch. `selected` holds the ids pre-checked; `detected` maps ids to what
    detect() found. Returns the chosen ids in registry order, or None when the user backs out."""
    selected = set(selected)
    ids = [a.ID for a in adapters]
    while True:
        print()
        print("Which agents should be watched?")
        for number, adapter in enumerate(adapters, 1):
            mark = "x" if adapter.ID in selected else " "
            print(f"  [{mark}] {number}) {adapter.NAME:<22} {detected.get(adapter.ID) or 'not found'}")
        try:
            answer = input(f"Toggle with 1-{len(ids)} (a: all, n: none), Enter to confirm: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not answer:
            return [i for i in ids if i in selected]
        for token in answer.replace(",", " ").split():
            if token == "a":
                selected = set(ids)
            elif token == "n":
                selected = set()
            elif token.isdigit() and 1 <= int(token) <= len(ids):
                selected ^= {ids[int(token) - 1]}


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
