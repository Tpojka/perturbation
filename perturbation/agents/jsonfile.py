"""Careful edits to JSON files that belong to an agent, not to us.

Every such file is read whole, changed in memory, backed up, and swapped in atomically. A file that can't
be parsed is left byte-identical and reported, because an agent once lost every setting to exactly that.
"""
import json
import os
import shutil

from .base import ConfigError

BACKUP_SUFFIX = ".perturbation.bak"


def read(path):
    """The file's JSON object, {} when it doesn't exist, ConfigError when it can't be used."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    try:
        data = json.loads(text) if text.strip() else {}
    except ValueError as error:
        raise ConfigError(f"{path} is not valid JSON ({error}). Left it untouched.")
    if not isinstance(data, dict):
        raise ConfigError(f"{path} does not hold a JSON object. Left it untouched.")
    return data


def update(path, change, skip_if_missing=False, delete_when_empty=False):
    """Apply `change(data)` to the file. Returns True when the file changed.

    `change` edits the dict in place. With `delete_when_empty`, a file left with no keys is removed —
    right for files that only ever held our entries.
    """
    if skip_if_missing and not path.exists():
        return False
    data = read(path)
    before = json.dumps(data, sort_keys=True)
    change(data)
    if json.dumps(data, sort_keys=True) == before:
        return False
    if path.exists():
        shutil.copy2(path, str(path) + BACKUP_SUFFIX)
        if delete_when_empty and not data:
            path.unlink()
            return True
    write(path, data)
    return True


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write beside the file and swap it in, so a crash can't leave the agent with half a config.
    tmp = path.with_name(path.name + ".perturbation.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def command_matches(entry, markers):
    """True when a hook entry's command names one of `markers`."""
    command = entry.get("command", "") if isinstance(entry, dict) else ""
    return any(marker in str(command) for marker in markers)


def strip_groups(hooks, markers):
    """Remove our entries from a {event: [{matcher, hooks: [...]}]} table (Claude Code's shape).

    Groups left empty are dropped, and so are events left without groups. Returns how many were removed.
    """
    removed = 0
    for event in list(hooks):
        groups = []
        for group in hooks[event]:
            if not isinstance(group, dict):
                groups.append(group)
                continue
            kept = [h for h in group.get("hooks", []) if not command_matches(h, markers)]
            removed += len(group.get("hooks", [])) - len(kept)
            if kept:
                groups.append({**group, "hooks": kept})
        if groups:
            hooks[event] = groups
        else:
            del hooks[event]
    return removed


def count_groups(hooks, markers):
    """How many entries in a grouped table are ours."""
    return sum(
        1
        for groups in hooks.values()
        if isinstance(groups, list)
        for group in groups
        if isinstance(group, dict)
        for h in group.get("hooks", [])
        if command_matches(h, markers)
    )
