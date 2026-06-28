"""The normalized event every adapter emits, plus the small set of node/edge
vocabularies. Keeping these whitelisted is what lets us build Cypher with
dynamic labels/types safely on Neo4j Community (no APOC)."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

# Node labels and edge types are whitelisted. Anything outside these sets is
# rejected at ingestion so we never interpolate untrusted strings into Cypher.
ENTITY_TYPES = {
    "Person", "Document", "Meeting", "Project", "Email", "Decision", "Task",
}
EVENT_TYPES = {
    "EDITED", "ATTENDED", "SENT", "RECEIVED", "PRODUCED", "REFERENCES",
    "ATTACHED", "DECIDED", "COMMITTED",
}


class WorkEvent(BaseModel):
    """The atomic unit of the graph. The edge IS the event.

    Every event carries an identity (auto-derived from content), a confidence
    score (1.0 = authoritative, < 1.0 = inferred), and a source attribution so
    provenance is never lost. The identity is what makes re-ingestion safe:
    MERGE on (event_id) instead of blind CREATE.
    """

    type: str                       # one of EVENT_TYPES — becomes the rel type
    actor: str                      # email of the Person who did it
    entity_id: str                  # stable id, e.g. "doc::/Documents/q2.docx"
    entity_type: str                # one of ENTITY_TYPES — becomes the label
    at: datetime
    title: str | None = None        # human-readable label for the entity node
    duration: float | None = None   # seconds, for EDITED
    event_id: str | None = None     # auto-derived hash if absent; the dedup key
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)  # 1.0=authoritative, <1.0=inferred
    source: str = "manual"          # adapter name: "filesystem", "git", "imap", "llm", ...
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _derive_event_id(self):
        if not self.event_id:
            payload = f"{self.type}|{self.actor}|{self.entity_id}|{self.at.isoformat()}"
            self.event_id = hashlib.sha256(payload.encode()).hexdigest()[:16]
        return self

    @field_validator("type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        v = v.upper()
        if v not in EVENT_TYPES:
            raise ValueError(f"unknown event type {v!r}; allowed: {sorted(EVENT_TYPES)}")
        return v

    @field_validator("entity_type")
    @classmethod
    def _known_entity(cls, v: str) -> str:
        v = v.capitalize() if v.islower() else v
        if v not in ENTITY_TYPES:
            raise ValueError(f"unknown entity type {v!r}; allowed: {sorted(ENTITY_TYPES)}")
        return v

    @field_validator("at")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        # Always store UTC-aware datetimes so decay math is unambiguous.
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)
