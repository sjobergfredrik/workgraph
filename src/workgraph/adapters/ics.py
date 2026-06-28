"""ICS calendar adapter — imports an .ics file into Meeting nodes and ATTENDED
edges. Each event becomes a Meeting; the organizer and every attendee become
Persons who ATTENDED it (at the meeting's start time, so future_boost applies
to upcoming meetings)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from icalendar import Calendar

from ..models import WorkEvent


def _email(value) -> str | None:
    s = str(value)
    return s.split("mailto:", 1)[1].lower() if "mailto:" in s.lower() else None


def _as_dt(value) -> datetime | None:
    dt = getattr(value, "dt", None)
    if dt is None:
        return None
    if not isinstance(dt, datetime):  # all-day event -> date
        dt = datetime(dt.year, dt.month, dt.day)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class IcsAdapter:
    name = "ics"

    def __init__(self, ics_path: str):
        self.ics_path = Path(ics_path).expanduser()

    def events(self) -> Iterator[WorkEvent]:
        cal = Calendar.from_ical(self.ics_path.read_bytes())
        for comp in cal.walk("VEVENT"):
            start = _as_dt(comp.get("DTSTART"))
            if start is None:
                continue
            uid = str(comp.get("UID", ""))
            summary = str(comp.get("SUMMARY", "(untitled meeting)"))
            entity_id = f"meeting::{uid or summary}"

            people: set[str] = set()
            if (org := comp.get("ORGANIZER")) is not None:
                if e := _email(org):
                    people.add(e)
            attendees = comp.get("ATTENDEE")
            if attendees is not None:
                for a in (attendees if isinstance(attendees, list) else [attendees]):
                    if e := _email(a):
                        people.add(e)

            for email in people or {"unknown@local"}:
                yield WorkEvent(
                    type="ATTENDED",
                    actor=email,
                    entity_id=entity_id,
                    entity_type="Meeting",
                    at=start,
                    title=summary,
                    source="ics",
                    confidence=1.0,
                    metadata={"uid": uid, "location": str(comp.get("LOCATION", ""))},
                )
