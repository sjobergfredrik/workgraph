# WorkGraph

*Your work, as a graph. Event-driven. Temporally aware. Yours.*

An event-driven work graph on Neo4j with temporal decay ranking. Nodes are work
entities (Person, Document, Meeting, Project, Email, Decision, Task); **edges are
events**, not relationships — the edge *is* the activity. A decay function
(WorkRank) surfaces what's relevant *now*, not everything that exists.

The thesis: Microsoft's Copilot advantage isn't the model, it's the **graph** —
the context layer connecting your email, calendar, docs and meetings. WorkGraph
is that layer, but open, self-hostable, and owned by you.

> Status: **v0.1, pre-product.** The goal before any pitch is that it has run on
> real work data for a week and proved useful. Single-user, local-first, no UI
> beyond the Neo4j Browser — remote sources (filesystem, git, calendar, email)
> are *pulled into* your local graph, never the other way around. See [SPEC.md](SPEC.md).

## Quick start

```bash
cp .env.example .env          # point WATCH_DIR at the dir you want watched
docker compose up -d          # Neo4j on :7474 (browser) / :7687 (bolt)

# run the CLI inside the app container
docker compose exec workgraph workgraph init
docker compose exec workgraph workgraph seed examples/seed_events.json
docker compose exec workgraph workgraph rank
```

Or run the CLI locally against the Dockerised Neo4j:

```bash
pip install -e ".[dev]"
export NEO4J_URI=bolt://localhost:7687
export NEO4J_PASSWORD=workgraph
workgraph init
workgraph seed examples/seed_events.json
workgraph rank
```

### Daily use

`workgraph watch` is a **long-running process** — it blocks and streams `EDITED`
events as you touch files, until you stop it with Ctrl-C. Point it at one or more
directories and leave it running in a dedicated terminal tab:

```bash
workgraph watch ~/Development ~/Documents ~/Desktop
```

Then, in a *different* tab, ingest batch sources and check what's prominent:

```bash
workgraph import-git ~/Development/some-repo --since "90 days ago"
workgraph import-ics ~/calendar.ics
workgraph rank
```

> Tip: `workgraph watch` never returns — don't chain commands after it in one
> paste. On zsh, also avoid trailing `# comments` on a command line; zsh passes
> them as arguments. For unattended, reboot-proof watching see
> [Run it durably](#run-it-durably-macos).

### Email via IMAP

Configure accounts in `~/.workgraph/workgraph.yaml` (gitignored — **never** the
tracked repo config). A template lives in [`config/workgraph.yaml`](config/workgraph.yaml):

```yaml
imap:
  accounts:
    - name: work
      host: imap.gmail.com
      port: 993
      user: you@example.com
      password: "<app-password>"
      folders: [INBOX, "[Gmail]/Sent Mail"]
```

```bash
workgraph import-imap --since-days 30 --limit 50   # start small
workgraph import-imap                               # all accounts, full pull
```

The sender `SENT` each message and every recipient `RECEIVED` it, so correspondent
prominence emerges from email volume. Gmail / Google Workspace needs an
[App Password](https://myaccount.google.com/apppasswords) (2-Step Verification on).
Microsoft 365 often disables IMAP Basic Auth at the tenant level — if login fails,
that account needs an OAuth2 adapter (not yet built).

### Day-1 commands

| Command | What it does |
|---------|--------------|
| `workgraph init` | Create the self Person node + schema constraints |
| `workgraph watch <dirs...>` | Live-watch one or more dirs, stream `EDITED` events |
| `workgraph import-ics ~/cal.ics` | Import meetings + attendees |
| `workgraph import-git <repo>` | Import commits as `COMMITTED` events |
| `workgraph import-imap` | Pull mail via IMAP → `SENT`/`RECEIVED` events |
| `workgraph add-event ...` | Manual escape hatch for any event |
| `workgraph seed <file.json>` | Bulk-load events (demo / testing) |
| `workgraph rank` | Compute WorkRank, print top prominent nodes |
| `workgraph offboard anna@ex.com` | Mark inactive, redistribute residual weight |
| `workgraph stats` | Node/edge/people counts |
| `workgraph graph` | Open the Neo4j Browser |

API: `uvicorn workgraph.api:app` → `GET /context` returns the currently-prominent
nodes (i.e. what you'd feed an LLM as "what I'm working on now").

## WorkRank

```
score(edge) = base_weight(type, duration) × time_factor(age)

time_factor:  age ≤ 30d → 1.0 · 30–90d → linear 1.0→0.3 · >90d → 0.1
              upcoming 0–8 days → ×1.5 (the week ahead surfaces)
prominence(node) = Σ score(edge) over all incident edges
```

All knobs live in [`config/workgraph.yaml`](config/workgraph.yaml) — tune them
while it runs. The scoring functions are pure (`src/workgraph/workrank.py`) and
unit-tested.

## v0.1 design decisions

These were the load-bearing choices the spec left open (see [SPEC.md](SPEC.md#decisions-v01)):

1. **Entity identity** — path-based id (`doc::<abs-path>`) + size/mtime
   fingerprint for later rename-stitching. Git uses git's own rename tracking.
2. **Base weights** — config YAML per event type; `EDITED` log-damped by edit
   duration so a deep edit outranks a glance but an idle window can't dominate.
3. **Offboarding** — proportional redistribution of a leaver's residual weight
   to co-contributors; sole-authored docs flagged `orphaned_knowledge`.

## Run it durably (macOS)

To keep the watcher running across reboots, install it as a LaunchAgent:

```bash
./deploy/install-launchagent.sh ~/Development ~/Documents ~/Desktop
```

It auto-starts at login, restarts on crash, and logs to `~/.workgraph/watch.log`.
Neo4j returns after a reboot via `restart: unless-stopped` (set Docker Desktop to
start at login).

> **Full Disk Access is required.** A `launchd` agent receives *no* filesystem
> events for user folders until you grant Full Disk Access to the interpreter it
> runs. In **System Settings → Privacy & Security → Full Disk Access**, add
> `…/workgraph/.venv/bin/python3.x` (press ⌘⇧G in the file dialog to paste the
> full path), then restart the agent. The venv is built with `--copies` so this
> is a stable, project-local path. Without this the agent runs but captures nothing.

```bash
launchctl print     gui/$(id -u)/se.andhumans.workgraph.watch    # status
launchctl kickstart -k gui/$(id -u)/se.andhumans.workgraph.watch # restart
launchctl bootout   gui/$(id -u)/se.andhumans.workgraph.watch    # stop
```

## Develop

```bash
make test      # unit tests, no Neo4j needed
make up        # start containers
make seed rank # load demo data + rank
```

## Security

WorkGraph is **local-first by design** — Neo4j runs in Docker bound to localhost
and your data never leaves your machine. Two notes:

- The default Neo4j password (`workgraph`) is a convenience for local dev only.
  **If you ever expose Neo4j beyond localhost, change it** — set `NEO4J_PASSWORD`
  (and `NEO4J_AUTH` in `docker-compose.yml`) to something real.
- `config/workgraph.yaml` may end up holding your own email and paths. It's
  tracked here with placeholders only; keep real config in `~/.workgraph/` or a
  `*.local.yaml` (both gitignored).

## License

Licensed under the [Apache License 2.0](LICENSE) — permissive, with an explicit
patent grant. See [NOTICE](NOTICE).
