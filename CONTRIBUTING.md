# Contributing

WorkGraph is built around a thin adapter pattern. The fastest way to make it more
useful is to **add an event source**.

## The adapter contract

Every source does one job: turn its native activity into a stream of normalized
`WorkEvent`s. That's it. See `src/workgraph/adapters/base.py`:

```python
class Adapter(Protocol):
    name: str
    def events(self) -> Iterator[WorkEvent]: ...
```

A `WorkEvent` (see `src/workgraph/models.py`):

```json
{
  "type": "EDITED",
  "actor": "fredrik@example.com",
  "entity_id": "doc::q2-strategy",
  "entity_type": "Document",
  "at": "2026-06-26T11:42:00Z",
  "title": "Q2-strategy.docx",
  "duration": 5400,
  "metadata": {}
}
```

- `type` must be in `EVENT_TYPES`, `entity_type` in `ENTITY_TYPES`
  (whitelists in `models.py`). This is what keeps Cypher injection-safe on
  Community Edition without APOC. Need a new type? Add it to the whitelist and
  give it a base weight in `config/workgraph.yaml`.
- `entity_id` must be **stable**: the same real-world thing must always produce
  the same id. The convention is `<kind>::<stable-key>` (`doc::`, `meeting::`).
- `at` is the time the event happened. Future-dated events (upcoming meetings)
  are fine — they get the `future_boost`.

## Adding a source

1. Create `src/workgraph/adapters/<name>.py` implementing `events()`.
2. Export it from `adapters/__init__.py`.
3. Wire a CLI command in `cli.py` (`import-<name>` for batch, or a watcher).
4. Add a test if the parsing has any logic worth pinning.

Existing examples: `filesystem.py` (live watcher), `git_log.py` (batch parse),
`ics.py` (file import).

## Post-MVP source ideas

Microsoft Graph webhooks · Google Workspace · Nextcloud activity API · IMAP
email · **DeltaLake transaction log** (the txn log *is* an event stream — a
natural fit for the adapter pattern over a data platform).

## Tests

```bash
make test   # pure-function tests for WorkRank + offboarding, no Neo4j needed
```

Keep scoring and redistribution logic pure (no DB calls) so it stays testable.
