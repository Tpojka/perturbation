"""The browser registry: every browser module, in order, and lookup by id.

To add a browser, write a module implementing the contract in `base.py` and add its name to MODULES.
"""
import importlib

from . import base

MODULES = ("chrome", "edge", "brave", "opera", "vivaldi", "arc", "chromium")

DEFAULT = "chrome"

_registry = None


def known():
    """Every browser adapter, sorted by its ORDER."""
    global _registry
    if _registry is None:
        modules = [base.check(importlib.import_module(f".{name}", __name__)) for name in MODULES]
        ids = [m.ID for m in modules]
        if len(set(ids)) != len(ids):
            raise TypeError(f"duplicate browser ids: {ids}")
        _registry = sorted(modules, key=lambda m: (m.ORDER, m.ID))
    return list(_registry)


def ids():
    return [m.ID for m in known()]


def get(browser_id):
    """The browser with this id, or None."""
    for module in known():
        if module.ID == browser_id:
            return module
    return None


def some(browser_ids):
    """The named browsers, in registry order, skipping ids this build doesn't know."""
    wanted = set(browser_ids)
    return [m for m in known() if m.ID in wanted]


def supported():
    """The browsers that can be registered on this OS."""
    return [m for m in known() if base.supported(m)]


def detected():
    """{id: where it was found} for every browser this OS can register and the machine has.

    A leftover profile counts as found, and says so: it is worth showing in the picker, never worth
    ticking on the user's behalf.
    """
    found = {}
    for module in supported():
        where = base.detect(module)
        if where:
            found[module.ID] = where
    return found


def installed():
    """The ids of the browsers whose application is really here, which is what gets pre-checked."""
    return [m.ID for m in supported() if base.app(m)]
