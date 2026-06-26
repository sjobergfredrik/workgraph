"""Thin FastAPI layer for future UI / AI-context consumption.

    uvicorn workgraph.api:app --reload

The /context endpoint is the one that matters: it returns the currently-prominent
nodes, which is exactly what you'd feed an LLM as "what Fredrik is working on now".
"""
from __future__ import annotations

from fastapi import FastAPI

from .config import load_config
from .db import Graph
from .models import WorkEvent

app = FastAPI(title="WorkGraph", version="0.1.0")


def _graph() -> Graph:
    return Graph(load_config())


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/context")
def context(limit: int = 20):
    """The point of the whole thing: what's prominent right now."""
    g = _graph()
    g.compute_workrank()
    rows = g.top_nodes(limit)
    g.close()
    return {"context": rows}


@app.get("/stats")
def stats():
    g = _graph()
    with g.session() as s:
        nodes = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        edges = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
    g.close()
    return {"nodes": nodes, "edges": edges}


@app.post("/events")
def add_event(event: WorkEvent):
    g = _graph()
    g.ingest(event)
    g.close()
    return {"ingested": 1}
