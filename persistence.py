"""Append-only write log for crash recovery: one JSON-encoded command per line."""

import json
import os
from pathlib import Path
from typing import Callable, TextIO


class PersistenceLog:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._file: TextIO = open(self._path, "a", encoding="utf-8")

    def append(self, args: list[str]) -> None:
        self._file.write(json.dumps(args) + "\n")
        self._file.flush()
        os.fsync(self._file.fileno())

    def close(self) -> None:
        self._file.close()


def replay(path: str | Path, apply: Callable[[list[str]], None]) -> None:
    path = Path(path)
    if not path.exists():
        return

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            apply(json.loads(line))
