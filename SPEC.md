# WorkGraph — Specification v0.1
> An event-driven work graph on Neo4j with temporal decay ranking.
> Open source. Self-hostable. Built to be tested on yourself first.

---

## Origin
This spec emerged from a conversation about digital sovereignty, the structural
failure of open source office suites to match Microsoft 365 Copilot's context
continuity, and what it would take to build that context layer without depending
on any hyperscaler.

The insight: Microsoft's AI advantage isn't the model — it's the graph. Copilot
knows your week because Microsoft Graph connects your email, calendar, documents
and meetings into one data model. WorkGraph is that layer, but open,
event-driven, and owned by you.

---

## Core Concept
A personal (and team) work graph where:
- **Nodes** are work entities: Person, Document, Meeting, Project, Email, Decision, Task
- **Edges are events**, not relationships — the edge *is* the activity
- **Temporal decay** surfaces what's relevant now, not what exists

```cypher
(:Person)-[:EDITED {at: datetime, duration: seconds, weight: float}]->(:Document)
(:Person)-[:ATTENDED {at: datetime}]->(:Meeting)
(:Meeting)-[:PRODUCED]->(:Document)
(:Person)-[:SENT {at: datetime}]->(:Email)-[:REFERENCES]->(:Document)
```

No fat ontology. No pre-modeled relationships. Events accumulate and the graph
self-organizes.

---

## WorkRank — Temporal Decay Scoring
A ranking function applied to edge weights based on recency:

```
score(edge) = base_weight × decay(age)
decay(age_days) =
  if age_days <= 30:  1.0                        # full weight, recent past
  if age_days in [31..90]: linear decay to 0.3   # present but fading
  if age_days > 90: 0.1                           # archived, still traversable
future_boost(days_ahead) =
  if days_ahead in [0..8]: 1.5                    # upcoming window gets a boost
```

The resulting node prominence = sum of WorkRank scores across all incident edges.
Prominent nodes surface in UI and AI context. Low-prominence nodes remain in the
graph but are visually and contextually deprioritized.

---

## Offboarding Ingestion
When a team member leaves:
1. Their Person node is marked `active: false` and disconnected from new events
2. A snapshot of their subgraph is computed: all Documents, Projects, Meetings
   they shared with remaining members
3. For each shared entity, the **residual weight** of their edges is redistributed
   to co-contributors
4. Documents they were the *sole* contributor to get flagged: `orphaned_knowledge: true`

This means: when Anna leaves, the Q2-strategy.docx you both edited becomes
*heavier* in your graph — you are now its sole bearer. The graph surfaces
institutional memory at the moment of risk, not after the fact.

---

## Event Sources (v0.1 — local first)

| Source | Method | Notes |
|--------|--------|-------|
| Local filesystem | File watcher (watchdog) | Tracks document edits by path |
| Git commits | Git log parser | Maps commits to Person + Document nodes |
| Calendar (ICS) | ICS file import | Meetings + attendees |
| Manual CLI | `workgraph add-event` | Escape hatch for anything |

Future sources (post-MVP): Microsoft Graph webhooks, Google Workspace, Nextcloud
activity API, email (IMAP).

The ingestion layer uses a thin adapter pattern — each source emits a normalized
`WorkEvent`:

```json
{
  "type": "EDITED",
  "actor": "fredrik@example.com",
  "entity_id": "doc::q2-strategy",
  "entity_type": "Document",
  "at": "2026-06-26T11:42:00Z",
  "metadata": {}
}
```

---

## Stack
- **Neo4j** — local via Docker, Community Edition
- **Python 3.11+** — ingestion, WorkRank computation, CLI
- **FastAPI** — thin API layer for future UI/AI consumption
- **Typer** — CLI for manual event injection and graph queries

See [README.md](README.md) for the Day-1 checklist and commands.

### First useful query
```cypher
MATCH (p:Person {self: true})-[e]->(n)
WHERE e.at > datetime() - duration('P30D')
RETURN n.title, n.type, sum(e.base_weight) AS prominence
ORDER BY prominence DESC
LIMIT 20
```

---

## What This Is Not (v0.1)
- Not a UI — Neo4j Browser is the UI for now
- Not multi-user — single person, local machine
- Not connected to cloud sources yet
- Not a product — it's a personal infrastructure experiment

---

## Decisions v0.1
These were the load-bearing choices the original spec left open. They were
settled before code because they're the parts you can't cleanly retrofit.

### 1. Entity identity — path-id + fingerprint
`entity_id = doc::<absolute-normalized-path>`. A size+mtime fingerprint is stored
in edge metadata so a later adapter can stitch renames into a single node. A bare
filesystem rename produces a new node for now; the **git adapter** sidesteps this
by relying on git's own rename tracking (`git log -M`).
*Rejected:* content-hash ids (every edit spawns a new node), inode ids (break
across machines/copies).

### 2. Base weights — config YAML + duration scaling
Per-event-type base weights live in `config/workgraph.yaml`, tunable without a
code change during the trial week. `EDITED` edges are scaled by edit duration,
log-damped: `factor = 1 + log1p(seconds)/log1p(reference)`, capped. A deep edit
outranks a glance; a 4-hour idle window can't dominate.
*Rejected:* count-based (ignores the spec's `duration` field), hardcoded
constants (no tuning during the week you most want to tune).

### 3. Offboarding — proportional redistribution, unit-tested
A leaver's residual weight on each shared entity is redistributed to remaining
co-contributors **in proportion to their existing weight** on that entity.
Sole-authored entities can't be redistributed → flagged `orphaned_knowledge`.
Implemented as a pure function (`offboard.py`) and unit-tested on a synthetic
three-person graph, so it's verifiable without a real team.
*Rejected:* defer the math (loses a distinctive idea), equal split (ignores who
actually carried the work).

---

## Open Source Positioning
**Repo:** `workgraph` · **License:** MIT
**Tagline:** *Your work, as a graph. Event-driven. Temporally aware. Yours.*

Ships with: `docker-compose.yml` (zero-config start), this `SPEC.md`,
`examples/` (seed events + Cypher), `CONTRIBUTING.md` (adapter pattern).

---

## Connection to Broader Context
This work graph is the missing context layer in the sovereign workspace stack.
Nextcloud + Euro-Office can store your files. WorkGraph makes them *findable by
proximity to your current work*, without sending your data to Azure.

It is also directly relevant to organizations running DeltaLake-based data
platforms (like Uppsala kommun) — DeltaLake's transaction log is itself an event
stream. WorkGraph's adapter pattern can sit on top of it, turning data platform
activity into organizational memory.

---

## Next Steps
1. ~~Create repo, push SPEC.md~~ → scaffolded
2. ~~Build minimal Docker Compose + Python skeleton~~ → done (ingestion + WorkRank + offboarding)
3. Run on own filesystem for 7 days
4. Write a short "what I learned" note for the README
5. Share with Torbjörn Berglund at Uppsala kommun as a conversation starter — not a pitch

---
*Spec authored: 2026-06-26 · Status: scaffolded, pre-trial*
