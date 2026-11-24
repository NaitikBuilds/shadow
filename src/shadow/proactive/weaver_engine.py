"""Cross-Project Insight Weaver Engine (C13).

Surfaces non-obvious connections between distinct projects by analyzing
the knowledge graph for semantic overlap and shared concepts.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from shadow.config import phase4_config

if TYPE_CHECKING:
    from shadow.memory.store import MemoryStore


class ProjectId(str):
    """Strong type for project identifiers."""

    pass


@dataclass(frozen=True)
class InsightCandidate:
    """A cross-project insight awaiting validation."""

    source_project: str
    target_project: str
    source_entity: int
    target_entity: int
    similarity: float
    source_evidence: list[int]  # observation IDs
    target_evidence: list[int]  # observation IDs


@dataclass(frozen=True)
class CrossProjectInsight:
    """Stored insight with provenance."""

    insight_id: int
    status: str  # 'new', 'saved', 'dismissed', 'cancelled'
    source_project: str
    target_project: str
    statement: str  # generated text
    created_at: int
    evidence: dict  # {'source_evidence': [...], 'target_evidence': [...]}


class WeaverState(Enum):
    RUNNING = "running"
    COMPLETE = "complete"
    CANCELLED = "cancelled"


class WeaverEngine:
    """Orchestrates cross-project insight generation."""

    PROJECT_CONSENT_CHANNEL = "weaver"

    def __init__(self, memory: MemoryStore, config: dict | None = None):
        self.memory = memory
        self.cfg = phase4_config(config or {})
        self._state: WeaverState | None = None
        self._cancelled = False

    # -----------------------------------------------------------------------
    # Eligibility Check
    # -----------------------------------------------------------------------
    def is_eligible(self) -> bool:
        """Check if weaver is globally eligible.

        Must pass all checks:
        1. weaver_enabled = True
        2. At least 2 distinct projects in KG
        3. Sufficient recent observations in both
        """
        if not self.cfg.get("weaver_enabled", False):
            return False

        # Check minimum project count
        projects = self._get_distinct_projects()
        if len(projects) < 2:
            return False

        # Check each project has recent activity
        now = int(time.time())
        lookback = self.cfg.get("weaver_state_days", 90) * 86400
        return all(self._has_recent_activity(proj, now - lookback, now) for proj in projects)

    # -----------------------------------------------------------------------
    # Exclusions Handling
    # -----------------------------------------------------------------------
    def get_exclusions(self) -> set[str]:
        """Return the set of excluded project names (case-insensitive)."""
        excluded = set(self.cfg.get("weaver_excluded_projects", []))
        # Normalize to lowercase for case-insensitive matching
        return {p.lower() for p in excluded}

    def is_project_excluded(self, project_name: str) -> bool:
        """Check if a project is in the exclusion list."""
        return project_name.lower() in self.get_exclusions()

    # -----------------------------------------------------------------------
    # Candidate Generation
    # -----------------------------------------------------------------------
    def generate_candidates(self) -> list[InsightCandidate]:
        """Generate cross-project insight candidates."""
        projects = self._get_distinct_projects(exclude_excluded=True)
        if len(projects) < 2:
            return []

        candidates: list[InsightCandidate] = []
        min_conf = self.cfg.get("weaver_min_confidence", 0.6)
        max_cands = self.cfg.get("weaver_max_candidates_per_run", 20)

        # Build entity index per project
        project_entities = self._index_entities_by_project()

        # Compare pairs of projects
        for i, src_proj in enumerate(projects):
            if self._cancelled:
                break
            for tgt_proj in projects[i + 1 :]:
                if self._cancelled:
                    break
                pairs = self._find_overlapping_entities(
                    project_entities.get(src_proj, {}),
                    project_entities.get(tgt_proj, {}),
                )
                for src_e, tgt_e, sim in pairs:
                    if sim >= min_conf:
                        evidence = self._gather_evidence(src_e, tgt_e)
                        candidates.append(
                            InsightCandidate(
                                source_project=src_proj,
                                target_project=tgt_proj,
                                source_entity=src_e,
                                target_entity=tgt_e,
                                similarity=sim,
                                source_evidence=evidence["source"],
                                target_evidence=evidence["target"],
                            )
                        )

                        if len(candidates) >= max_cands:
                            return candidates

        return candidates

    # -----------------------------------------------------------------------
    # Internal Helpers
    # -----------------------------------------------------------------------
    def _get_distinct_projects(self, exclude_excluded: bool = False) -> list[str]:
        """Return list of distinct project names from knowledge graph."""
        excluded = self.get_exclusions() if exclude_excluded else set()
        cur = self.memory.conn.cursor()
        cur.execute("SELECT DISTINCT name FROM entities WHERE type = 'project' ORDER BY name")
        projects = [row[0] for row in cur.fetchall()]
        if exclude_excluded:
            projects = [p for p in projects if p.lower() not in excluded]
        return projects

    def _has_recent_activity(self, project: str, start: int, end: int) -> bool:
        """Check if a project has observations in the given time range."""
        cur = self.memory.conn.cursor()
        # Use strftime to convert Unix epoch to ISO string for comparison
        # SQLite stores timestamps as DATETIME strings
        cur.execute(
            """
            SELECT COUNT(*) FROM observations o
            JOIN observation_entities oe ON o.id = oe.observation_id
            JOIN entities e ON oe.entity_id = e.id
            WHERE e.type = 'project' AND e.name = ?
            AND o.timestamp >= datetime(?, 'unixepoch')
            """,
            (project, start),
        )
        count = cur.fetchone()[0]
        return count >= 1

    def _index_entities_by_project(self) -> dict[str, dict[int, dict]]:
        """Build a project -> entity_id -> entity dict index."""
        cur = self.memory.conn.cursor()
        cur.execute(
            """
            SELECT e.id, e.type, e.name, e.last_seen
            FROM entities e
            WHERE e.type = 'project' OR e.type IN ('topic', 'file')
            """
        )
        entities: dict[str, dict[int, dict]] = {}
        excluded = self.get_exclusions()

        for row in cur.fetchall():
            ent_id, ent_type, ent_name, last_seen = row
            # Find which project(s) this entity belongs to via co-occurrence edges
            cur.execute(
                """
                SELECT e2.name FROM edges ed
                JOIN entities e2 ON ed.source_id = e2.id
                WHERE ed.target_id = ? AND e2.type = 'project'
                """,
                (ent_id,),
            )
            projects = [r[0] for r in cur.fetchall()]
            if not projects:
                # Entity is directly tagged as a project
                if ent_type == "project":
                    projects = [ent_name]

            for proj in projects:
                if proj.lower() in excluded:
                    continue
                if proj not in entities:
                    entities[proj] = {}
                entities[proj][ent_id] = {
                    "type": ent_type,
                    "name": ent_name,
                    "last_seen": last_seen,
                }

        return entities

    def _find_overlapping_entities(
        self, src_idx: dict[int, dict], tgt_idx: dict[int, dict]
    ) -> list[tuple[int, int, float]]:
        """Find entities with shared context between two project indices."""
        # For simplicity, use co-occurrence graph traversal
        # Find entities that share topics or have weak edges between them
        overlaps: list[tuple[int, int, float]] = []

        # Get all entity pairs and check for co_occurs edges
        all_src = list(src_idx.keys())
        all_tgt = list(tgt_idx.keys())

        for src_id in all_src:
            cur = self.memory.conn.cursor()
            cur.execute(
                """
                SELECT e.id, COUNT(ed.id) as shared
                FROM entities e
                JOIN edges ed ON e.id = ed.target_id
                WHERE ed.source_id = ? AND e.id IN (?)
                GROUP BY e.id
                """,
                (src_id, tuple(all_tgt)),
            )
            for tgt_id, shared in cur.fetchall():
                if shared > 0:
                    # Simple similarity: shared edges / total possible
                    sim = min(1.0, shared / max(1, len(all_src)))
                    overlaps.append((src_id, tgt_id, sim))

        return overlaps

    def _gather_evidence(self, src_eid: int, tgt_eid: int) -> dict[str, list[int]]:
        """Gather observation IDs that evidence these entities."""
        cur = self.memory.conn.cursor()
        result = {"source": [], "target": []}

        cur.execute(
            "SELECT observation_id FROM observation_entities WHERE entity_id = ?",
            (src_eid,),
        )
        result["source"] = [r[0] for r in cur.fetchall()]

        cur.execute(
            "SELECT observation_id FROM observation_entities WHERE entity_id = ?",
            (tgt_eid,),
        )
        result["target"] = [r[0] for r in cur.fetchall()]

        return result

    # -----------------------------------------------------------------------
    # Run Management
    # -----------------------------------------------------------------------
    def start_run(self) -> str | None:
        """Start a weaving run. Returns run_id or None if already running."""
        if not self.is_eligible():
            return None
        self._state = WeaverState.RUNNING
        self._cancelled = False
        # In production, this would write to a weaver_runs table
        return f"weaver-{int(time.time())}"

    def cancel_run(self) -> None:
        """Cancel an in-progress run."""
        self._cancelled = True

    def complete_run(self, cancelled: bool = False) -> None:
        """Mark run as complete or cancelled."""
        if cancelled:
            self._state = WeaverState.CANCELLED
        else:
            self._state = WeaverState.COMPLETE

    def record_insight(self, insight: CrossProjectInsight) -> int:
        """Persist an insight to the weaver_insights table."""
        cur = self.memory.conn.cursor()
        cur.execute(
            """
            INSERT INTO weaver_insights
            (status, source_project, target_project, statement, created_at, evidence)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                insight.status,
                insight.source_project,
                insight.target_project,
                insight.statement,
                insight.created_at,
                str(insight.evidence),
            ),
        )
        self.memory.conn.commit()
        return cur.lastrowid
