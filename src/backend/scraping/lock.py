"""Non-blocking process lock so hourly and manual scrapes cannot overlap.

Ported from JobWatch. Windows uses ``msvcrt.locking``, POSIX uses ``fcntl.flock``.
"""

from __future__ import annotations

import os
from pathlib import Path


class RunAlreadyActive(RuntimeError):
    pass


class RunLock:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.stream = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("a+b")
        try:
            if self.path.stat().st_size == 0:
                self.stream.seek(0)
                self.stream.write(b"0")
                self.stream.flush()
            if os.name == "nt":
                import msvcrt

                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            self.stream.close()
            self.stream = None
            raise RunAlreadyActive(f"another scrape run holds {self.path}") from exc
        return self

    def __exit__(self, *_):
        if self.stream is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        finally:
            self.stream.close()
            self.stream = None
