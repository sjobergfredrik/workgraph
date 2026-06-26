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

# Files we never want as nodes.
IGNORE_SUFFIXES = {".tmp", ".swp", ".part", ".crdownload", ".DS_Store"}
IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".next"}
MAX_EDIT_GAP_SECONDS = 1800  # cap the "duration" proxy at 30 min


def _ignored(path: Path) -> bool:
    if path.suffix in IGNORE_SUFFIXES or path.name in IGNORE_SUFFIXES:
        return True
    return any(part in IGNORE_DIRS for part in path.parts)


class _Handler(FileSystemEventHandler):
    def __init__(self, actor: str, sink):
        self.actor = actor
        self.sink = sink
        self._last_seen: dict[str, float] = {}

    def _emit(self, path_str: str):
        path = Path(path_str)
        if path.is_dir() or _ignored(path):
            return
        now = time.time()
        prev = self._last_seen.get(path_str)
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
    """Live watcher. Calls `on_event(WorkEvent)` for each edit until stopped."""

    name = "filesystem"

    def __init__(self, path: str, actor: str):
        self.path = path
        self.actor = actor

    def watch(self, on_event) -> None:
        handler = _Handler(self.actor, on_event)
        observer = Observer()
        observer.schedule(handler, self.path, recursive=True)
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
