"""Configuration loading. Reads workgraph.yaml (overridable via WORKGRAPH_CONFIG)
and lets a few env vars win so Docker can inject Neo4j credentials."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATHS = [
    os.environ.get("WORKGRAPH_CONFIG"),
    "/config/workgraph.yaml",          # Docker mount
    str(Path.home() / ".workgraph" / "workgraph.yaml"),
    str(Path(__file__).resolve().parents[2] / "config" / "workgraph.yaml"),
]


@dataclass
class Config:
    raw: dict[str, Any] = field(default_factory=dict)
    path: Path | None = None

    # --- Neo4j -------------------------------------------------------------
    @property
    def neo4j_uri(self) -> str:
        return os.environ.get("NEO4J_URI") or self.raw["neo4j"]["uri"]

    @property
    def neo4j_user(self) -> str:
        return os.environ.get("NEO4J_USER") or self.raw["neo4j"]["user"]

    @property
    def neo4j_password(self) -> str:
        return os.environ.get("NEO4J_PASSWORD") or self.raw["neo4j"]["password"]

    # --- Self --------------------------------------------------------------
    @property
    def self_email(self) -> str:
        return self.raw["self"]["email"]

    @property
    def self_name(self) -> str:
        return self.raw["self"].get("name", self.self_email)

    # --- Scoring knobs (passed straight into workrank) ----------------------
    @property
    def weights(self) -> dict[str, float]:
        return {k: float(v) for k, v in self.raw.get("weights", {}).items()}

    @property
    def duration_scaling(self) -> dict[str, float]:
        return self.raw.get("duration_scaling", {})

    @property
    def decay(self) -> dict[str, float]:
        return self.raw.get("decay", {})

    @property
    def future_boost(self) -> dict[str, float]:
        return self.raw.get("future_boost", {})


def load_config(path: str | os.PathLike | None = None) -> Config:
    candidates = [path] + DEFAULT_CONFIG_PATHS if path else DEFAULT_CONFIG_PATHS
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            p = Path(candidate)
            return Config(raw=yaml.safe_load(p.read_text()) or {}, path=p)
    raise FileNotFoundError(
        "No workgraph.yaml found. Looked in: "
        + ", ".join(str(c) for c in candidates if c)
    )
