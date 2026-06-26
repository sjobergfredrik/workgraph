"""Neo4j access layer. Builds Cypher with dynamic labels/rel-types using only
whitelisted vocabulary (see models.ENTITY_TYPES / EVENT_TYPES), so this works
on Community Edition without APOC and never interpolates untrusted strings."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

from neo4j import GraphDatabase

from .config import Config
from .models import ENTITY_TYPES, EVENT_TYPES, WorkEvent
from . import workrank


class Graph:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._driver = GraphDatabase.driver(
            cfg.neo4j_uri,
            auth=(cfg.neo4j_user, cfg.neo4j_password),
            # An empty/young graph legitimately lacks some property keys; the
            # resulting "property does not exist" warnings are just noise.
            notifications_min_severity="OFF",
        )

    def close(self) -> None:
        self._driver.close()

    @contextmanager
    def session(self):
        with self._driver.session() as s:
            yield s

    # --- schema / init ------------------------------------------------------
    def ensure_constraints(self) -> None:
        stmts = [
            "CREATE CONSTRAINT person_id IF NOT EXISTS FOR (p:Person) REQUIRE p.id IS UNIQUE",
        ] + [
            f"CREATE CONSTRAINT {t.lower()}_id IF NOT EXISTS "
            f"FOR (n:{t}) REQUIRE n.id IS UNIQUE"
            for t in ENTITY_TYPES if t != "Person"
        ]
        with self.session() as s:
            for stmt in stmts:
                s.run(stmt)

    def init_self(self) -> None:
        with self.session() as s:
            s.run(
                "MERGE (p:Person {id: $email}) "
                "SET p.self = true, p.name = $name, p.active = true",
                email=self.cfg.self_email, name=self.cfg.self_name,
            )

    # --- ingestion ----------------------------------------------------------
    def ingest(self, event: WorkEvent) -> None:
        if event.entity_type not in ENTITY_TYPES or event.type not in EVENT_TYPES:
            raise ValueError("event failed vocabulary whitelist")
        w = workrank.base_weight(event.type, event.duration, self.cfg.weights)
        # Labels/types validated against whitelist above -> safe to interpolate.
        cypher = (
            "MERGE (p:Person {id: $actor}) "
            "ON CREATE SET p.active = true "
            f"MERGE (n:{event.entity_type} {{id: $entity_id}}) "
            "SET n.title = coalesce($title, n.title, $entity_id), n.type = $entity_type "
            f"CREATE (p)-[r:{event.type} {{at: datetime($at), base_weight: $w, "
            "duration: $duration}]->(n) "
            "SET r += $metadata"
        )
        with self.session() as s:
            s.run(
                cypher,
                actor=event.actor,
                entity_id=event.entity_id,
                entity_type=event.entity_type,
                title=event.title,
                at=event.at.isoformat(),
                w=w,
                duration=event.duration,
                metadata={f"meta_{k}": v for k, v in event.metadata.items()},
            )

    def ingest_many(self, events) -> int:
        n = 0
        for e in events:
            self.ingest(e)
            n += 1
        return n

    # --- WorkRank -----------------------------------------------------------
    def _all_edges(self) -> list[dict]:
        q = (
            "MATCH (p:Person)-[r]->(n) "
            "RETURN p.id AS actor, n.id AS entity_id, type(r) AS type, "
            "r.at AS at, r.base_weight AS base_weight, r.duration AS duration"
        )
        out = []
        with self.session() as s:
            for rec in s.run(q):
                at = rec["at"]
                # neo4j DateTime -> python datetime
                at = at.to_native() if hasattr(at, "to_native") else at
                out.append({
                    "actor": rec["actor"],
                    "entity_id": rec["entity_id"],
                    "type": rec["type"],
                    "at": at,
                    "weight": rec["base_weight"],
                    "duration": rec["duration"],
                })
        return out

    def compute_workrank(self, now: datetime | None = None) -> dict[str, float]:
        """Compute prominence per node and write it back as n.prominence so the
        Neo4j Browser can ORDER BY it."""
        now = now or datetime.now(timezone.utc)
        edges = self._all_edges()
        scores = workrank.prominence(
            edges, now=now,
            weights=self.cfg.weights,
            decay_cfg=self.cfg.decay,
            future_cfg=self.cfg.future_boost,
            duration_cfg=self.cfg.duration_scaling,
        )
        with self.session() as s:
            for entity_id, score in scores.items():
                s.run(
                    "MATCH (n {id: $id}) SET n.prominence = $score",
                    id=entity_id, score=round(score, 4),
                )
        return scores

    def top_nodes(self, limit: int = 10) -> list[dict]:
        q = (
            "MATCH (n) WHERE n.prominence IS NOT NULL "
            "RETURN n.title AS title, n.type AS type, n.prominence AS prominence, "
            "n.orphaned_knowledge AS orphaned "
            "ORDER BY n.prominence DESC LIMIT $limit"
        )
        with self.session() as s:
            return [dict(r) for r in s.run(q, limit=limit)]

    # --- offboarding --------------------------------------------------------
    def offboard(self, leaver: str, apply: bool = True) -> list:
        from .offboard import redistribute
        edges = self._all_edges()
        plan = redistribute(leaver, edges)
        if apply:
            with self.session() as s:
                s.run(
                    "MATCH (p:Person {id: $leaver}) SET p.active = false",
                    leaver=leaver,
                )
                for item in plan:
                    if item.orphaned_knowledge:
                        s.run(
                            "MATCH (n {id: $id}) SET n.orphaned_knowledge = true",
                            id=item.entity_id,
                        )
                    else:
                        for actor, delta in item.deltas.items():
                            s.run(
                                "MATCH (p:Person {id: $actor})-[r]->(n {id: $id}) "
                                "WITH r LIMIT 1 "
                                "SET r.base_weight = r.base_weight + $delta",
                                actor=actor, id=item.entity_id, delta=round(delta, 4),
                            )
        return plan
