from datetime import datetime, timedelta, timezone

from workgraph import workrank as wr

NOW = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)


def test_decay_full_then_fade_then_floor():
    assert wr.decay(0) == 1.0
    assert wr.decay(30) == 1.0
    # midpoint of fade band (day 60) -> halfway between 1.0 and 0.3
    assert abs(wr.decay(60) - 0.65) < 1e-9
    assert abs(wr.decay(90) - 0.3) < 1e-9
    assert wr.decay(120) == 0.1
    assert wr.decay(3650) == 0.1


def test_decay_is_monotonic_nonincreasing():
    prev = 1.1
    for age in range(0, 200, 5):
        cur = wr.decay(age)
        assert cur <= prev + 1e-12
        prev = cur


def test_future_boost_window():
    assert wr.future_boost(0) == 1.5
    assert wr.future_boost(8) == 1.5
    assert wr.future_boost(9) == 1.0
    assert wr.future_boost(30) == 1.0


def test_time_factor_past_vs_future():
    past = NOW - timedelta(days=200)
    near_future = NOW + timedelta(days=3)
    far_future = NOW + timedelta(days=40)
    assert wr.time_factor(past, NOW) == 0.1
    assert wr.time_factor(near_future, NOW) == 1.5
    assert wr.time_factor(far_future, NOW) == 1.0


def test_duration_factor_dampened_and_capped():
    assert wr.duration_factor(None) == 1.0
    assert wr.duration_factor(0) == 1.0
    # ~1h of editing ≈ factor 2.0
    assert abs(wr.duration_factor(3600) - 2.0) < 0.05
    # a 10h idle window must not run away — capped at max_factor
    assert wr.duration_factor(36000) <= 3.0


def test_edited_uses_duration_a_deep_edit_beats_a_glance():
    weights = {"EDITED": 1.0}
    glance = wr.score_edge("EDITED", NOW, 2, now=NOW, weights=weights)
    deep = wr.score_edge("EDITED", NOW, 3600, now=NOW, weights=weights)
    assert deep > glance


def test_prominence_uses_stored_weight_when_present():
    # A stored "weight" (e.g. after offboarding redistribution) must be honored
    # directly, not recomputed from type+duration. Regression guard: this is
    # what makes offboarding actually move the ranking.
    past = NOW - timedelta(days=5)  # clearly past -> decay 1.0, no future boost
    edges = [{"entity_id": "doc::a", "type": "EDITED", "at": past,
              "duration": 3600, "weight": 99.0}]
    scores = wr.prominence(edges, now=NOW, weights={"EDITED": 1.0})
    assert abs(scores["doc::a"] - 99.0) < 1e-9  # stored weight x time_factor(1.0)


def test_prominence_sums_incident_edges():
    weights = {"EDITED": 1.0, "ATTENDED": 2.0}
    edges = [
        {"entity_id": "doc::a", "type": "EDITED", "at": NOW, "duration": 3600},
        {"entity_id": "doc::a", "type": "EDITED", "at": NOW, "duration": 2},
        {"entity_id": "meet::x", "type": "ATTENDED", "at": NOW},
    ]
    scores = wr.prominence(edges, now=NOW, weights=weights)
    assert set(scores) == {"doc::a", "meet::x"}
    assert scores["doc::a"] > scores["meet::x"]  # two edits, one deep
