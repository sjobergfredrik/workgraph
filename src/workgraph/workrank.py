"""WorkRank — temporal decay scoring.

These are deliberately pure functions of (event, now, config). No Neo4j here,
so the scoring logic can be unit-tested in isolation and tuned with confidence.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Iterable

# ---- defaults (mirrors config/workgraph.yaml) ------------------------------
DEFAULT_DECAY = {"full_until_days": 30, "fade_until_days": 90, "fade_floor": 0.3, "floor": 0.1}
DEFAULT_FUTURE = {"window_days": 8, "factor": 1.5}
DEFAULT_DURATION = {"reference_seconds": 3600, "max_factor": 3.0}


def decay(age_days: float, cfg: dict | None = None) -> float:
    """Weight multiplier for a PAST edge, given its age in days.

        age <= full_until            -> 1.0
        full_until < age <= fade_until -> linear from 1.0 to fade_floor
        age > fade_until             -> floor
    """
    c = {**DEFAULT_DECAY, **(cfg or {})}
    full, fade = c["full_until_days"], c["fade_until_days"]
    fade_floor, floor = c["fade_floor"], c["floor"]
    if age_days <= full:
        return 1.0
    if age_days <= fade:
        span = fade - full
        progressed = (age_days - full) / span if span else 1.0
        return 1.0 - progressed * (1.0 - fade_floor)
    return floor


def future_boost(days_ahead: float, cfg: dict | None = None) -> float:
    """Multiplier for an UPCOMING edge. Inside the window -> boost, else 1.0."""
    c = {**DEFAULT_FUTURE, **(cfg or {})}
    if 0 <= days_ahead <= c["window_days"]:
        return c["factor"]
    return 1.0


def time_factor(at: datetime, now: datetime | None = None, *, decay_cfg=None, future_cfg=None) -> float:
    """Single entry point: decay for the past, boost for the near future."""
    now = now or datetime.now(timezone.utc)
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    delta_days = (at - now).total_seconds() / 86400.0
    if delta_days >= 0:
        return future_boost(delta_days, future_cfg)
    return decay(-delta_days, decay_cfg)


def duration_factor(seconds: float | None, cfg: dict | None = None) -> float:
    """Log-damped multiplier for EDITED edges. None/0 -> 1.0 (no signal)."""
    if not seconds or seconds <= 0:
        return 1.0
    c = {**DEFAULT_DURATION, **(cfg or {})}
    ref = c["reference_seconds"]
    factor = 1.0 + math.log1p(seconds) / math.log1p(ref)
    return min(factor, c["max_factor"])


def base_weight(event_type: str, duration: float | None, weights: dict[str, float]) -> float:
    """Base weight for an edge before temporal effects, with duration scaling
    applied to EDITED edges."""
    w = weights.get(event_type, 1.0)
    if event_type == "EDITED":
        w *= duration_factor(duration)
    return w


def score_edge(
    event_type: str,
    at: datetime,
    duration: float | None,
    *,
    now: datetime | None = None,
    weights: dict[str, float] | None = None,
    decay_cfg: dict | None = None,
    future_cfg: dict | None = None,
    duration_cfg: dict | None = None,
) -> float:
    """score(edge) = base_weight x time_factor."""
    weights = weights or {}
    w = weights.get(event_type, 1.0)
    if event_type == "EDITED":
        w *= duration_factor(duration, duration_cfg)
    return w * time_factor(at, now, decay_cfg=decay_cfg, future_cfg=future_cfg)


def prominence(edges: Iterable[dict], *, now=None, weights=None, decay_cfg=None,
               future_cfg=None, duration_cfg=None) -> dict[str, float]:
    """Sum WorkRank scores per entity_id across all incident edges.

    Each edge dict needs: entity_id, type, at. If the edge carries a stored
    "weight" (the base_weight persisted at ingestion — which already folds in
    duration scaling AND any offboarding redistribution), that is used directly
    and only time_factor is applied on top. Otherwise the base weight is
    recomputed from (type, duration) so callers can score raw events.
    """
    weights = weights or {}
    scores: dict[str, float] = {}
    for e in edges:
        bw = e.get("weight")
        if bw is None:
            bw = base_weight(e["type"], e.get("duration"), weights)
        s = bw * time_factor(e["at"], now, decay_cfg=decay_cfg, future_cfg=future_cfg)
        scores[e["entity_id"]] = scores.get(e["entity_id"], 0.0) + s
    return scores
