"""Shared helpers for adapters that read files from an inbox folder."""

from __future__ import annotations

import re
from pathlib import Path

_UNSAFE = re.compile(r"[^\w .()\-]")


def list_inbox(inbox: Path, patterns: tuple[str, ...]) -> list[Path]:
    """Files matching any pattern, sorted by name. Skips hidden files and Excel
    lock files (~$name.xlsx)."""
    if not inbox.is_dir():
        return []
    found = {p for pattern in patterns for p in inbox.glob(pattern) if p.is_file()}
    return sorted((p for p in found if not p.name.startswith((".", "~$"))),
                  key=lambda p: p.name)


def payload_name(original: str) -> str:
    """Snapshot-safe file name; keeps Turkish letters, spaces and the extension."""
    name = _UNSAFE.sub("_", original)
    return name if re.match(r"^\w", name) else f"_{name}"
