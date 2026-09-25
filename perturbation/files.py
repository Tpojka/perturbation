"""Reading and writing a file so that no reader ever sees half of it, or nothing at all.

The trick is the same everywhere - write a temporary file beside the target, then rename over it - but
Windows makes both sides of it fail under contention, because Python opens files without
FILE_SHARE_DELETE: the writer's rename is denied while a reader has the file open, and a reader's open
is denied while the rename is in flight. Readers here are frequent (one hook process per agent event,
one host process per browser polling twice a second), so both sides retry for a moment rather than give
up. Windows CI found both, with several threads reading config.json while one wrote it - the second one
as a reader that saw no file at all and fell back to the defaults.
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


def read(target, encoding="utf-8"):
    """The file's text, or None when it isn't there.

    A reader that is merely too early gets another go: on Windows an open during a rename is refused
    rather than answered, and treating that as "no file" is how the defaults crept in.
    """
    deadline = time.monotonic() + RETRY_SECONDS
    while True:
        try:
            return target.read_text(encoding=encoding)
        except (FileNotFoundError, IsADirectoryError):
            return None
        except PermissionError:
            if time.monotonic() >= deadline:
                return None  # a reader never raises: the caller's fallback is better than a traceback
            time.sleep(RETRY_PAUSE)
        except OSError:
            return None


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
