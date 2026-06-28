"""Idempotent ingestion and event provenance tests."""
import json
from datetime import datetime, timedelta, timezone

from workgraph.models import WorkEvent
from workgraph import workrank as wr

NOW = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)


def test_event_id_is_auto_derived():
    """Every event gets a deterministic, content-based id even if none provided."""
    e1 = WorkEvent(type="EDITED", actor="fredrik@ex.com",
                   entity_id="doc::a", entity_type="Document", at=NOW)
    assert e1.event_id is not None
    assert len(e1.event_id) == 16
    # Same content -> same id
    e2 = WorkEvent(type="EDITED", actor="fredrik@ex.com",
                   entity_id="doc::a", entity_type="Document", at=NOW)
    assert e2.event_id == e1.event_id, "deterministic — same content = same id"


def test_event_id_differs_on_content():
    """Different type, actor, entity or time -> different id."""
    base = dict(type="EDITED", actor="fredrik@ex.com",
                entity_id="doc::a", entity_type="Document", at=NOW)
    a = WorkEvent(**base)
    b = WorkEvent(**{**base, "type": "COMMITTED"})
    c = WorkEvent(**{**base, "actor": "anna@ex.com"})
    d = WorkEvent(**{**base, "entity_id": "doc::b"})
    e = WorkEvent(**{**base, "at": NOW - timedelta(days=1)})
    ids = {a.event_id, b.event_id, c.event_id, d.event_id, e.event_id}
    assert len(ids) == 5, "different content -> different ids"


def test_event_id_is_stable_roundtrip():
    """JSON roundtrip preserves auto-derived event_id."""
    e = WorkEvent(type="EDITED", actor="fredrik@ex.com",
                  entity_id="doc::a", entity_type="Document", at=NOW,
                  source="filesystem", confidence=1.0)
    via_json = WorkEvent(**json.loads(e.model_dump_json()))
    assert via_json.event_id == e.event_id
    assert via_json.source == "filesystem"
    assert via_json.confidence == 1.0


def test_default_confidence_and_source():
    """Events carry confidence=1.0 and source='manual' by default."""
    e = WorkEvent(type="EDITED", actor="fredrik@ex.com",
                  entity_id="doc::x", entity_type="Document", at=NOW)
    assert e.confidence == 1.0
    assert e.source == "manual"


def test_confidence_dampens_prominence():
    """Two identical events except confidence — the lower-confidence one ranks lower."""
    past = NOW - timedelta(days=5)  # clearly past -> decay=1.0, no future boost
    weights = {"EDITED": 10.0}  # large weight to make the difference clear
    edges = [
        {"entity_id": "doc::a", "type": "EDITED", "at": past,
         "duration": None, "confidence": 1.0},
        {"entity_id": "doc::b", "type": "EDITED", "at": past,
         "duration": None, "confidence": 0.5},
    ]
    scores = wr.prominence(edges, now=NOW, weights=weights)
    assert abs(scores["doc::a"] - 10.0) < 1e-9   # confidence=1.0, full weight
    assert abs(scores["doc::b"] - 5.0) < 1e-9    # confidence=0.5, half weight


def test_confidence_in_score_edge():
    """score_edge() multiplies base_weight × time_factor × confidence."""
    past = NOW - timedelta(days=5)  # before the future_boost window
    w = wr.score_edge("EDITED", past, None, now=NOW,
                      weights={"EDITED": 2.0}, confidence=0.8)
    assert abs(w - 1.6) < 1e-9  # 2.0 × 1.0 × 0.8


def test_prominence_confidence_defaults_to_one():
    """Edges without explicit confidence (e.g. old seed data) default to 1.0."""
    past = NOW - timedelta(days=5)
    edges = [
        {"entity_id": "doc::a", "type": "EDITED", "at": past, "duration": None},
    ]
    scores = wr.prominence(edges, now=NOW, weights={"EDITED": 1.0})
    assert abs(scores["doc::a"] - 1.0) < 1e-9  # defaults to confidence=1.0