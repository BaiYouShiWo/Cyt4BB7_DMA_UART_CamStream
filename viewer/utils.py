"""Utility functions shared across modules."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Final

TIMESTAMP_FORMAT: Final[str] = "%Y%m%d_%H%M%S"


def timestamp_string(when: float | None = None) -> str:
    """Return a filesystem-safe timestamp string.

    Args:
        when: Unix timestamp. Defaults to the current time.

    Returns:
        A string formatted as ``YYYYMMDD_HHMMSS``.
    """
    if when is None:
        when = time.time()
    return datetime.fromtimestamp(when).strftime(TIMESTAMP_FORMAT)


def ensure_directory(path: Path) -> None:
    """Create ``path`` if it does not already exist."""
    path.mkdir(parents=True, exist_ok=True)


def next_filename(directory: Path, prefix: str, extension: str) -> Path:
    """Generate a unique timestamped file path inside ``directory``.

    Args:
        directory: Directory in which to create the file.
        prefix: Filename prefix (e.g. ``frame`` or ``video``).
        extension: File extension including the leading dot.

    Returns:
        A non-existing :class:`Path` using the current timestamp.
    """
    ensure_directory(directory)
    base = directory / f"{prefix}_{timestamp_string()}{extension}"
    if not base.exists():
        return base

    # In the unlikely event of a collision, append a counter.
    counter = 1
    while True:
        candidate = directory / f"{prefix}_{timestamp_string()}_{counter}{extension}"
        if not candidate.exists():
            return candidate
        counter += 1
