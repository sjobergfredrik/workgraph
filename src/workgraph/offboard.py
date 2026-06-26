"""Offboarding — redistribute a departing person's residual edge weight to the
people who remain, and flag the knowledge only they held.

The redistribution math is a pure function so it can be unit-tested on a
synthetic graph without a running Neo4j or a real team.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EntityRedistribution:
    entity_id: str
    leaver_weight: float                       # residual weight the leaver held
    orphaned_knowledge: bool                   # leaver was the SOLE contributor
    deltas: dict[str, float] = field(default_factory=dict)  # email -> added weight


def redistribute(
    leaver: str,
    edges: list[dict],
) -> list[EntityRedistribution]:
    """Given all edges in the graph (each: actor, entity_id, weight), compute,
    per entity the leaver touched, how their residual weight flows to the
    co-contributors.

    Strategy: proportional. Each remaining co-contributor receives the leaver's
    residual weight in proportion to their OWN existing weight on that entity.
    A document the leaver was the sole contributor to cannot be redistributed —
    it gets flagged orphaned_knowledge instead (institutional memory at risk).
    """
    # Aggregate weight per (entity, actor).
    by_entity: dict[str, dict[str, float]] = {}
    for e in edges:
        by_entity.setdefault(e["entity_id"], {})
        by_entity[e["entity_id"]][e["actor"]] = (
            by_entity[e["entity_id"]].get(e["actor"], 0.0) + float(e.get("weight", 1.0))
        )

    results: list[EntityRedistribution] = []
    for entity_id, actors in by_entity.items():
        if leaver not in actors:
            continue
        leaver_weight = actors[leaver]
        others = {a: w for a, w in actors.items() if a != leaver}
        total_other = sum(others.values())

        if total_other <= 0:
            results.append(EntityRedistribution(
                entity_id=entity_id,
                leaver_weight=leaver_weight,
                orphaned_knowledge=True,
            ))
            continue

        deltas = {a: leaver_weight * (w / total_other) for a, w in others.items()}
        results.append(EntityRedistribution(
            entity_id=entity_id,
            leaver_weight=leaver_weight,
            orphaned_knowledge=False,
            deltas=deltas,
        ))
    return results
