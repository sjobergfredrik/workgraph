"""Adapter contract. Every event source — filesystem, git, ICS, manual — does
one job: turn its native activity into a stream of normalized WorkEvents.

Add a new source by implementing `events()` and documenting it in CONTRIBUTING.md.
"""
from __future__ import annotations

from typing import Iterator, Protocol

from ..models import WorkEvent


class Adapter(Protocol):
    name: str

    def events(self) -> Iterator[WorkEvent]:
        """Yield normalized WorkEvents. May be finite (batch import) or block
        forever (live watcher)."""
        ...
