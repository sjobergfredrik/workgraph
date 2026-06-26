"""Small shared helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def entity_id_for_path(path: str | Path) -> str:
    """Stable, path-based document id. Normalized to an absolute path so the
    same file always maps to the same node. Renames produce a new id for now;
    the fingerprint stored alongside lets a future adapter stitch them."""
    return f"doc::{Path(path).expanduser().resolve()}"
