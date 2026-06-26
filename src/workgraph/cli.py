"""WorkGraph CLI — the Day-1 surface.

    workgraph init
    workgraph watch ~/Documents
    workgraph import-ics ~/calendar.ics
    workgraph import-git ~/Development/some-repo
    workgraph add-event --type EDITED --entity doc::foo --entity-type Document
    workgraph rank
    workgraph offboard anna@example.com
    workgraph graph
"""
from __future__ import annotations

import json
import webbrowser
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .config import load_config
from .db import Graph
from .models import WorkEvent
from .util import now_utc

app = typer.Typer(add_completion=False, help="Your work, as a graph.")
console = Console()


def _graph() -> Graph:
    return Graph(load_config())


@app.command()
def init():
    """Create the self Person node and schema constraints."""
    g = _graph()
    g.ensure_constraints()
    g.init_self()
    console.print(f"[green]Initialized[/]. Self = {g.cfg.self_email}")
    g.close()


@app.command()
def watch(paths: list[str] = typer.Argument(..., help="one or more directories")):
    """Watch one or more directories and stream EDITED events (Ctrl-C to stop).

    Example: workgraph watch ~/Development ~/Documents ~/Desktop
    """
    from .adapters import FilesystemAdapter
    g = _graph()
    adapter = FilesystemAdapter(paths, g.cfg.self_email)
    console.print(f"[cyan]Watching[/] {', '.join(paths)} as {g.cfg.self_email}. Ctrl-C to stop.")
    count = 0

    def sink(event: WorkEvent):
        nonlocal count
        # Stay alive across transient DB outages (e.g. Neo4j restarting after a
        # reboot). Drop the event, log, and keep watching rather than crashing.
        try:
            g.ingest(event)
        except Exception as e:
            console.print(f"  [red]! skipped[/] {event.title}: {e}")
            return
        count += 1
        console.print(f"  + EDITED {event.title}  (events: {count})")

    try:
        adapter.watch(sink)
    finally:
        console.print(f"[green]Stopped[/]. Ingested {count} events.")
        g.close()


@app.command("import-ics")
def import_ics(ics_path: str):
    """Import meetings + attendees from an .ics file."""
    from .adapters import IcsAdapter
    g = _graph()
    n = g.ingest_many(IcsAdapter(ics_path).events())
    console.print(f"[green]Imported[/] {n} meeting events from {ics_path}")
    g.close()


@app.command("import-git")
def import_git(repo: str, since: Optional[str] = typer.Option(None, help="e.g. '90 days ago'")):
    """Import git commits as COMMITTED events."""
    from .adapters import GitAdapter
    g = _graph()
    n = g.ingest_many(GitAdapter(repo, since=since).events())
    console.print(f"[green]Imported[/] {n} commit events from {repo}")
    g.close()


@app.command("import-imap")
def import_imap(
    account: Optional[str] = typer.Option(None, help="only this account name"),
    since_days: int = typer.Option(90, help="how far back to fetch"),
    limit: Optional[int] = typer.Option(None, help="cap messages per folder"),
):
    """Pull mail via IMAP and emit SENT/RECEIVED events. Configure accounts in
    ~/.workgraph/workgraph.yaml (gitignored) — never in the tracked repo config."""
    from datetime import datetime, timedelta
    from .adapters import ImapAdapter
    g = _graph()
    accounts = g.cfg.imap_accounts
    if not accounts:
        console.print("[red]No imap.accounts configured.[/] Add them to "
                      "~/.workgraph/workgraph.yaml (see config/workgraph.yaml for the template).")
        g.close()
        raise typer.Exit(1)
    since = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")
    total = 0
    for acct in accounts:
        if account and acct.get("name") != account:
            continue
        console.print(f"[cyan]IMAP[/] {acct.get('name', acct['user'])} since {since} ...")
        try:
            n = g.ingest_many(ImapAdapter(acct, since=since, limit=limit).events())
            console.print(f"  imported {n} email events")
            total += n
        except Exception as e:
            console.print(f"  [red]failed[/]: {e}")
    console.print(f"[green]Done[/] — {total} email events total")
    g.close()


@app.command("add-event")
def add_event(
    type: str = typer.Option(..., "--type"),
    entity: str = typer.Option(..., "--entity"),
    entity_type: str = typer.Option(..., "--entity-type"),
    actor: Optional[str] = typer.Option(None, help="defaults to self"),
    title: Optional[str] = typer.Option(None),
    duration: Optional[float] = typer.Option(None),
):
    """Manual escape hatch — inject any WorkEvent."""
    g = _graph()
    g.ingest(WorkEvent(
        type=type, actor=actor or g.cfg.self_email, entity_id=entity,
        entity_type=entity_type, at=now_utc(), title=title, duration=duration,
    ))
    console.print(f"[green]Added[/] {type} -> {entity}")
    g.close()


@app.command()
def seed(path: str = typer.Argument("examples/seed_events.json")):
    """Load a JSON array of WorkEvents — handy for demos and offboarding tests."""
    g = _graph()
    data = json.loads(open(path).read())
    n = g.ingest_many(WorkEvent(**e) for e in data)
    console.print(f"[green]Seeded[/] {n} events from {path}")
    g.close()


@app.command()
def rank(limit: int = 10):
    """Run WorkRank and print the most prominent nodes right now."""
    g = _graph()
    g.compute_workrank()
    rows = g.top_nodes(limit)
    table = Table(title=f"Top {limit} by WorkRank")
    table.add_column("Prominence", justify="right", style="bold cyan")
    table.add_column("Type")
    table.add_column("Title")
    table.add_column("", style="red")
    for r in rows:
        flag = "ORPHANED" if r.get("orphaned") else ""
        table.add_row(f"{r['prominence']:.2f}", str(r.get("type") or ""),
                      str(r.get("title") or ""), flag)
    console.print(table)
    g.close()


@app.command()
def offboard(email: str, dry_run: bool = typer.Option(False, "--dry-run")):
    """Mark a person inactive and redistribute their residual weight."""
    g = _graph()
    plan = g.offboard(email, apply=not dry_run)
    orphaned = [p for p in plan if p.orphaned_knowledge]
    moved = [p for p in plan if not p.orphaned_knowledge]
    console.print(f"{'[yellow]DRY RUN[/] ' if dry_run else ''}"
                  f"Offboarded {email}: {len(moved)} entities redistributed, "
                  f"{len(orphaned)} flagged orphaned_knowledge.")
    for p in orphaned:
        console.print(f"  [red]orphaned[/] {p.entity_id} (was sole contributor)")
    g.close()


@app.command()
def graph():
    """Open the Neo4j Browser with a pre-loaded WorkRank query."""
    url = "http://localhost:7474"
    console.print(f"Opening {url} — paste the query from examples/queries.cypher")
    try:
        webbrowser.open(url)
    except Exception:
        pass


@app.command()
def stats():
    """Quick counts of what's in the graph."""
    g = _graph()
    with g.session() as s:
        nodes = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        edges = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        people = s.run("MATCH (p:Person) RETURN count(p) AS c").single()["c"]
    console.print(json.dumps({"nodes": nodes, "edges": edges, "people": people}, indent=2))
    g.close()


if __name__ == "__main__":
    app()
