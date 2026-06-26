from workgraph.adapters.imap import events_from_message

RAW = b"""\
From: Anna Example <anna@example.com>
To: Fredrik <me@example.com>, Bob <bob@example.com>
Cc: carol@example.com
Subject: Q2 strategy
Date: Fri, 20 Jun 2026 09:10:00 +0000
Message-ID: <abc123@example.com>

Body text here.
"""


def test_parses_sender_and_recipients():
    events = events_from_message(RAW)
    by_actor = {(e.type, e.actor) for e in events}
    assert ("SENT", "anna@example.com") in by_actor
    assert ("RECEIVED", "me@example.com") in by_actor
    assert ("RECEIVED", "bob@example.com") in by_actor
    assert ("RECEIVED", "carol@example.com") in by_actor  # Cc counts
    # one SENT + three RECEIVED
    assert sum(1 for e in events if e.type == "SENT") == 1
    assert sum(1 for e in events if e.type == "RECEIVED") == 3


def test_all_events_share_one_email_entity():
    events = events_from_message(RAW)
    ids = {e.entity_id for e in events}
    assert ids == {"email::abc123@example.com"}
    assert all(e.entity_type == "Email" for e in events)
    assert all(e.title == "Q2 strategy" for e in events)


def test_date_is_parsed_timezone_aware():
    e = events_from_message(RAW)[0]
    assert e.at.year == 2026 and e.at.month == 6 and e.at.day == 20
    assert e.at.tzinfo is not None


def test_message_without_id_or_date_is_skipped():
    assert events_from_message(b"From: x@y.com\nSubject: no id no date\n\nhi") == []
