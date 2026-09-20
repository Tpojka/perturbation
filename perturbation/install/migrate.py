"""Finds and removes the four projects this one subsumes: Claudication, Codexalgia, Copilonidal and
Antigravalgia. Each left a native host manifest, a data directory and hook entries in its agent's config.

Nothing is removed without listing it first. Chrome extensions can't uninstall each other, so the old
extension IDs are printed for the user to remove at chrome://extensions.
"""
import json
import os
import shutil
import sys
from pathlib import Path
from typing import List, NamedTuple, Optional

from .. import agents
from ..agents.base import ConfigError, describe
from . import system

PREDECESSORS = (
    {
        "name": "Claudication",
        "agent": "claude",
        "host": "com.tpojka.claudication",
        "extension_id": "hpoodlefheijkfkpebmooehgnjkibdnc",
        "markers": ("claudication.pyz", "claudication_hook.py", "claudication_notify.py"),
    },
    {
        "name": "Codexalgia",
        "agent": "codex",
        "host": "com.tpojka.codexalgia",
        "extension_id": "pdfldjccnohafaolkilhbnhjkeaineaa",
        "markers": ("codexalgia.pyz",),
    },
    {
        "name": "Copilonidal",
        "agent": "copilot",
        "host": "com.tpojka.copilonidal",
        "extension_id": "bkmgmoledlbikdmpgoaciefdkdokdnnl",
        "markers": ("copilonidal.pyz",),
    },
    {
        "name": "Antigravalgia",
        "agent": "antigravity",
        "host": "com.tpojka.antigravalgia",
        "extension_id": "bpfhgifephcgodfaicmamfpgpcikhidd",
        "markers": ("antigravalgia.pyz",),
    },
)


class Found(NamedTuple):
    name: str
    agent: str
    extension_id: str
    manifests: List[Path]
    data_dir: Optional[Path]
    hooks: Optional[str]  # where the agent's config still names the predecessor
    settings: dict  # notifications and sound carried over, when its config.json is readable

    def items(self):
        yield from (f"native host manifest {describe(m)}" for m in self.manifests)
        if self.data_dir:
            yield f"data directory {describe(self.data_dir)}"
        if self.hooks:
            yield f"hooks: {self.hooks}"


def data_dir_of(name):
    override = os.environ.get(f"{name.upper()}_HOME")
    if override:
        return Path(override)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / name
    if sys.platform == "win32":
        return Path(os.environ["LOCALAPPDATA"]) / name
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / name.lower()


def find():
    """Every predecessor that left something behind."""
    found = []
    for spec in PREDECESSORS:
        adapter = agents.get(spec["agent"])
        manifests = system.registered_manifests(spec["host"], data_dir_of(spec["name"]))
        data_dir = data_dir_of(spec["name"])
        try:
            hooks = adapter.installed(spec["markers"]) if adapter else None
        except ConfigError:
            hooks = None
        settings = {}
        try:
            old = json.loads((data_dir / "config.json").read_text(encoding="utf-8"))
            settings = {k: old[k] for k in ("notifications", "sound") if isinstance(old.get(k), bool)}
        except (OSError, ValueError, AttributeError):
            pass
        if manifests or data_dir.is_dir() or hooks:
            found.append(Found(spec["name"], spec["agent"], spec["extension_id"], manifests, data_dir if data_dir.is_dir() else None, hooks, settings))
    return found


def remove(found):
    """Remove one predecessor's hook entries, host manifests and data directory. Returns problems."""
    problems = []
    spec = next(s for s in PREDECESSORS if s["name"] == found.name)
    adapter = agents.get(found.agent)
    if found.hooks and adapter:
        try:
            adapter.uninstall(spec["markers"])
        except ConfigError as error:
            problems.append(str(error))
    system.unregister_host(spec["host"])
    if found.data_dir:
        shutil.rmtree(found.data_dir, ignore_errors=True)
    return problems


def carried_over(found):
    """notifications and sound from the first predecessor that recorded them."""
    for item in found:
        if item.settings:
            return item.settings
    return {}
