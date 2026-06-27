"""Filesystem adapter — watches a directory and emits EDITED events.

Entity identity is path-based (doc::<abs-path>) with a size/mtime fingerprint
stored in metadata, so a later adapter can stitch renames. `duration` is the
gap since the previous edit of the same file, capped, as a cheap proxy for
"time spent" (a real editor integration would report this directly).
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Iterator

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from ..models import WorkEvent
from ..util import entity_id_for_path, now_utc

# Files we never want as nodes (editor scratch, build artifacts, lockfiles).
IGNORE_SUFFIXES = {
    ".tmp", ".swp", ".part", ".crdownload", ".DS_Store",
    ".pyc", ".pyo", ".log", ".lock", ".map", ".o", ".class",
}
# Directories whose churn is noise, not work — caches and build output. Keeps
# filesystem-watching a busy ~/Development tree from flooding the graph.
IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".next",
    "dist", "build", "target", "out", "vendor", "coverage",
    ".turbo", ".cache", ".parcel-cache", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".gradle", ".idea", ".tox", "Pods", ".terraform",
}
MAX_EDIT_GAP_SECONDS = 1800  # cap the "duration" proxy at 30 min
# One logical save fires several raw events (create + modify + metadata) on
# macOS/watchdog. Collapse events for the same path within this window into the
# single EDITED already emitted, so a save counts once instead of inflating rank.
DEBOUNCE_SECONDS = 1.5


def _is_temp_name(name: str) -> bool:
    """Atomic-write / editor scratch files that get renamed onto the real file.
    Their *real* suffix is a pid/hash, so a suffix check alone misses them
    (e.g. 'README.md.tmp.81653.55d8ac3'). Match the tell-tale patterns instead."""
    return (
        ".tmp." in name                       # atomic writes: foo.tmp.<pid>.<hash>
        or name.endswith("~")                 # emacs/gedit backups
        or name.endswith(".crswap")           # crswap atomic saves
        or name.startswith(".#")              # emacs lock files
        or name.startswith("~$")              # Office lock files
        or ".sb-" in name                     # macOS sandbox atomic writes
    )


def _ignored(path: Path) -> bool:
    name = path.name
    if path.suffix in IGNORE_SUFFIXES or name in IGNORE_SUFFIXES:
        return True
    if _is_temp_name(name):
        return True
    return any(part in IGNORE_DIRS for part in path.parts)


class _Handler(FileSystemEventHandler):
    def __init__(self, actor: str, sink):
        self.actor = actor
        self.sink = sink
        self._last_seen: dict[str, float] = {}

    def _emit(self, path_str: str, now: float | None = None):
        path = Path(path_str)
        if path.is_dir() or _ignored(path):
            return
        now = time.time() if now is None else now
        prev = self._last_seen.get(path_str)
        # Debounce: an event landing within DEBOUNCE_SECONDS of the last *emitted*
        # edit is part of the same logical save — fold it into that one and bail.
        # `_last_seen` is left pointing at the emitted edit (not refreshed here), so
        # the duration of the next genuine save is the gap to it, and a stream of
        # saves still rate-limits to one EDITED per window instead of starving.
        if prev is not None and now - prev < DEBOUNCE_SECONDS:
            return
        duration = min(now - prev, MAX_EDIT_GAP_SECONDS) if prev else None
        self._last_seen[path_str] = now
        try:
            stat = path.stat()
            fp = {"size": stat.st_size, "mtime": int(stat.st_mtime)}
        except OSError:
            fp = {}
        self.sink(WorkEvent(
            type="EDITED",
            actor=self.actor,
            entity_id=entity_id_for_path(path),
            entity_type="Document",
            at=now_utc(),
            title=path.name,
            duration=duration,
            metadata={"fingerprint_size": fp.get("size"),
                      "fingerprint_mtime": fp.get("mtime"),
                      "path": str(path)},
        ))

    def on_modified(self, event: FileSystemEvent):
        if not event.is_directory:
            self._emit(event.src_path)

    def on_created(self, event: FileSystemEvent):
        if not event.is_directory:
            self._emit(event.src_path)


class FilesystemAdapter:
    """Live watcher over one or more directories. Calls `on_event(WorkEvent)`
    for each edit until stopped. A single _Handler is shared across all roots so
    debouncing is global per path."""

    name = "filesystem"

    def __init__(self, paths: str | list[str], actor: str):
        self.paths = [paths] if isinstance(paths, str) else list(paths)
        self.actor = actor

    def watch(self, on_event) -> None:
        handler = _Handler(self.actor, on_event)
        observer = Observer()
        for p in self.paths:
            observer.schedule(handler, str(Path(p).expanduser()), recursive=True)
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            observer.stop()
            observer.join()

    def events(self) -> Iterator[WorkEvent]:  # pragma: no cover - blocking
        collected: list[WorkEvent] = []
        self.watch(collected.append)
        yield from collected
