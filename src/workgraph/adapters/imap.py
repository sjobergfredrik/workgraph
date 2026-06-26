"""IMAP adapter — pulls mail from one or more IMAP accounts and emits SENT /
RECEIVED events linking People to Email nodes.

Model (symmetric, works for both Sent and Inbox folders): the sender SENT the
email; every recipient RECEIVED it. A thread between you and X therefore builds
both directions naturally — your sent mail gives (you)-[SENT]->(email),
(X)-[RECEIVED]->(email); X's reply in your inbox gives the mirror. Correspondent
prominence falls out of email volume, decayed by recency like everything else.

Credentials live ONLY in ~/.workgraph/workgraph.yaml (gitignored), never in the
tracked repo config. Uses stdlib imaplib + email — no new dependency.

Caveats:
- Gmail / Google Workspace: needs an App Password (2-Step Verification on).
- Microsoft 365: many tenants disable IMAP Basic Auth via Security Defaults; if
  login fails, the account likely requires OAuth2 (XOAUTH2) — a future adapter.
"""
from __future__ import annotations

import email
import imaplib
from datetime import timezone
from email.utils import getaddresses, parsedate_to_datetime
from typing import Iterator

from ..models import WorkEvent

MAX_RECIPIENTS = 25  # skip recipient fan-out beyond this (newsletters/lists)


def _addresses(msg, *headers) -> list[str]:
    raw: list[str] = []
    for h in headers:
        raw += msg.get_all(h, [])
    return [addr.lower() for _, addr in getaddresses(raw) if addr and "@" in addr]


def events_from_message(raw: bytes) -> list[WorkEvent]:
    """Pure parse: an RFC822 message -> SENT/RECEIVED WorkEvents. Returns [] if
    the message lacks the Message-ID or Date we need to anchor it."""
    msg = email.message_from_bytes(raw)
    msg_id = (msg.get("Message-ID") or "").strip().strip("<>")
    if not msg_id:
        return []
    try:
        at = parsedate_to_datetime(msg.get("Date"))
    except (TypeError, ValueError):
        return []
    if at is None:
        return []
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)

    entity_id = f"email::{msg_id}"
    subject = msg.get("Subject", "(no subject)")
    meta = {"message_id": msg_id}

    senders = _addresses(msg, "From")
    recipients = _addresses(msg, "To", "Cc")
    if len(recipients) > MAX_RECIPIENTS:
        recipients = []  # bulk mail — keep the SENT, drop the fan-out

    events: list[WorkEvent] = []
    for s in senders[:1]:
        events.append(WorkEvent(type="SENT", actor=s, entity_id=entity_id,
                                entity_type="Email", at=at, title=subject, metadata=meta))
    for r in recipients:
        events.append(WorkEvent(type="RECEIVED", actor=r, entity_id=entity_id,
                                entity_type="Email", at=at, title=subject, metadata=meta))
    return events


class ImapAdapter:
    name = "imap"

    def __init__(self, account: dict, *, since: str | None = None, limit: int | None = None):
        self.account = account
        self.since = since      # IMAP date string, e.g. "01-Jun-2026"
        self.limit = limit

    def events(self) -> Iterator[WorkEvent]:
        acct = self.account
        conn = imaplib.IMAP4_SSL(acct["host"], int(acct.get("port", 993)))
        conn.login(acct["user"], acct["password"])
        try:
            for folder in acct.get("folders", ["INBOX"]):
                status, _ = conn.select(f'"{folder}"', readonly=True)
                if status != "OK":
                    continue
                criteria = ["SINCE", self.since] if self.since else ["ALL"]
                status, data = conn.search(None, *criteria)
                if status != "OK" or not data or not data[0]:
                    continue
                ids = data[0].split()
                if self.limit:
                    ids = ids[-self.limit:]
                for num in ids:
                    status, msgdata = conn.fetch(num, "(RFC822)")
                    if status != "OK" or not msgdata or not msgdata[0]:
                        continue
                    yield from events_from_message(msgdata[0][1])
        finally:
            try:
                conn.logout()
            except Exception:
                pass
