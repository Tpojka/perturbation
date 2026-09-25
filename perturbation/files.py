"""Writing a file so that no reader ever sees half of it.

The trick is the same everywhere - write a temporary file beside the target, then rename over it - but
Windows refuses the rename while anyone has the target open, because Python opens files without
FILE_SHARE_DELETE. Readers here are frequent (one hook process per agent event, one host process per
browser polling twice a second), so the rename retries for a moment instead of failing. CI on Windows
found this with several threads reading config.json while one wrote it.
"""
import os
import threading
import time

RETRY_SECONDS = 1.0
RETRY_PAUSE = 0.01


def temp_name(target):
    """A temporary name of its own per writer, so two writers can't rename each other's file."""
    return target.with_name(f"{target.name}.{os.getpid()}.{threading.get_ident()}.tmp")


def replace(tmp, target):
    """Rename `tmp` over `target`, retrying while Windows says a reader has it open."""
    deadline = time.monotonic() + RETRY_SECONDS
    while True:
        try:
            os.replace(tmp, target)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(RETRY_PAUSE)


def write(target, text, encoding="utf-8"):
    """Put `text` in `target` in one step. The temporary file goes beside it, on the same filesystem."""
    tmp = temp_name(target)
    tmp.write_text(text, encoding=encoding)
    try:
        replace(tmp, target)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
