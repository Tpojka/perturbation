"""The adapter registry: every agent module, in order, and lookup by id.

To add an agent, write a module implementing the contract in `base.py` and add its name to MODULES.
"""
import importlib

from . import base

MODULES = ("claude", "codex", "copilot", "antigravity")

_registry = None


def registered():
    """Every adapter, sorted by its ORDER."""
    global _registry
    if _registry is None:
        modules = [base.check(importlib.import_module(f".{name}", __name__)) for name in MODULES]
        ids = [m.ID for m in modules]
        if len(set(ids)) != len(ids):
            raise TypeError(f"duplicate adapter ids: {ids}")
        _registry = sorted(modules, key=lambda m: (m.ORDER, m.ID))
    return list(_registry)


def ids():
    return [m.ID for m in registered()]


def get(agent_id):
    """The adapter with this id, or None."""
    for module in registered():
        if module.ID == agent_id:
            return module
    return None


def ordered(order):
    """Adapters in the user's order; ids missing from `order` follow in registry order."""
    by_id = {m.ID: m for m in registered()}
    result = [by_id[i] for i in order if i in by_id]
    result += [m for m in registered() if m not in result]
    return result
