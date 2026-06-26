"""Git adapter — parses `git log` into COMMITTED (Person->Document) events.

Leans on git's own rename tracking (`--follow`-style behaviour via -M on the
log), so file identity survives moves better than the filesystem watcher.
Author email becomes the Person; each changed file becomes a Document.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from ..models import WorkEvent

_SEP = "\x1f"  # unit separator, unlikely in commit metadata
_FMT = f"%H{_SEP}%ae{_SEP}%aI{_SEP}%s"


class GitAdapter:
    name = "git"

    def __init__(self, repo: str, since: str | None = None):
        self.repo = str(Path(repo).expanduser().resolve())
        self.since = since

    def events(self) -> Iterator[WorkEvent]:
        cmd = ["git", "-C", self.repo, "log", "-M", f"--pretty=format:{_FMT}", "--name-only"]
        if self.since:
            cmd.append(f"--since={self.since}")
        out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout

        commit = None
        for line in out.splitlines():
            if _SEP in line:
                sha, email, iso, subject = line.split(_SEP, 3)
                commit = {"sha": sha, "email": email,
                          "at": datetime.fromisoformat(iso).astimezone(timezone.utc),
                          "subject": subject}
            elif line.strip() and commit:
                path = (Path(self.repo) / line.strip()).resolve()
                yield WorkEvent(
                    type="COMMITTED",
                    actor=commit["email"],
                    entity_id=f"doc::{path}",
                    entity_type="Document",
                    at=commit["at"],
                    title=path.name,
                    metadata={"sha": commit["sha"], "subject": commit["subject"],
                              "repo": self.repo},
                )
