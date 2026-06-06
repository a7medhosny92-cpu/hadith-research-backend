"""Rebuild an index safely: build into a temp file, then atomically swap it in.

Two wins over deleting-then-rebuilding in place:
* the live index is replaced only once the new one is fully built (a failed build
  never leaves you with no index);
* on Windows, if the target is open in another process (the running app/uvicorn),
  you get a clear "close the app" message instead of a raw PermissionError traceback.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Protocol


class _Built(Protocol):
    def count(self) -> int: ...
    def close(self) -> None: ...


def rebuild(target: str | Path, build: Callable[[Path], _Built]) -> int:
    """``build(tmp_path)`` must create the index at ``tmp_path`` and return it (with
    ``.count()``/``.close()``). We then replace ``target`` and return the row count."""
    target = Path(target)
    tmp = target.with_name(target.name + ".tmp")
    if tmp.exists():
        tmp.unlink()
    index = build(tmp)
    try:
        count = index.count()
    finally:
        index.close()  # release our own handle so the swap can proceed
    try:
        os.replace(tmp, target)
    except PermissionError:
        tmp.unlink(missing_ok=True)
        raise SystemExit(
            f"\n[!] '{target.name}' is locked by another process.\n"
            f"    Close the running app (the desktop window or `uvicorn`) and "
            f"run the update again."
        )
    return count
