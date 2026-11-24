"""Cross-Project Insight Weaver Engine (C13-C14).

Surfaces non-obvious connections between distinct projects by analyzing
the knowledge graph for semantic overlap and shared concepts.

C13: Eligibility, exclusions, candidate generation
C14: Provenance, dedupe, staleness, persistence
"""

from __future__ import annotations

import hashlib
import json
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
    status: str  # 'new', 'saved', 'dismissed', 'cancelled', 'stale'
    source_project: str
    target_project: str
    statement: str  # generated text
    created_at: int
    updated_at: int
    evidence: dict  # {'source_evidence': [...], 'target_evidence': [...]}
    evidence_hash: str
    conflict_flag: int = 0


class WeaverState(Enum):
    RUNNING = "running"
    COMPLETE = "complete"
    CANCELLED = "cancelled"


class WeaverError(Exception):
    """Weaver-specific errors."""

    pass


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
        return all(
            self._has_recent_activity(proj, now - lookback, now) for proj in projects
        )

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
    # C14: Provenance & Persistence
    # -----------------------------------------------------------------------
    def compute_evidence_hash(
        self, source_evidence: list[int], target_evidence: list[int]
    ) -> str:
        """Compute SHA256 hash of normalized evidence for deduplication.

        Normalizes by sorting observation IDs to ensure order-independent hashing.
        """
        normalized = {
            "source": sorted(source_evidence),
            "target": sorted(target_evidence),
        }
        payload = json.dumps(normalized, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()[:32]

    def check_duplicate_insight(self, evidence_hash: str) -> int | None:
        """Check if an insight with this evidence hash already exists.

        Returns existing insight_id if found, None otherwise.
        Implements AC-P4-WVR-03: no duplicate on re-run with same evidence.
        """
        cur = self.memory.conn.cursor()
        cur.execute(
            "SELECT insight_id FROM weaver_insights WHERE evidence_hash = ?",
            (evidence_hash,),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def get_observation_hashes(
        self, observation_ids: list[int]
    ) -> dict[int, tuple[str, str]]:
        """Fetch content hashes and redacted snippets for observations.

        Returns dict mapping observation_id -> (content_hash, snippet).
        Snippet is truncated to 200 chars for privacy.
        """
        if not observation_ids:
            return {}

        placeholders = ",".join("?" * len(observation_ids))
        cur = self.memory.conn.cursor()
        cur.execute(
            f"SELECT id, content FROM observations WHERE id IN ({placeholders})",
            tuple(observation_ids),
        )

        result = {}
        for obs_id, content in cur.fetchall():
            # Hash the full content
            content_hash = hashlib.sha256(content.encode()).hexdigest()[:32]
            # Redacted snippet (first 200 chars)
            snippet = content[:200]
            result[obs_id] = (content_hash, snippet)
        return result

    def check_staleness(self, insight_id: int) -> bool:
        """Check if any source observations for an insight have been deleted.

        Implements AC-P4-WVR-09: source deleted → status=stale.
        Uses weaver_insight_sources as the source of truth - if a source record
        was deleted via CASCADE (observation deleted), the insight is stale.
        """
        cur = self.memory.conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM weaver_insight_sources WHERE insight_id = ?",
            (insight_id,),
        )
        source_count = cur.fetchone()[0]

        # Get expected count from weaver_insights.evidence
        cur.execute(
            "SELECT evidence FROM weaver_insights WHERE insight_id = ?",
            (insight_id,),
        )
        row = cur.fetchone()
        if not row:
            return False

        import json

        evidence = json.loads(row[0])
        expected_count = len(evidence.get("source_evidence", [])) + len(
            evidence.get("target_evidence", [])
        )

        # If source records were deleted (CASCADE), count will be less than expected
        return source_count < expected_count

    def detect_conflicting_evidence(
        self, source_evidence: list[int], target_evidence: list[int]
    ) -> int:
        """Detect if evidence sources contradict each other.

        For now, a simple heuristic: if source and target have overlapping
        observation IDs (shouldn't happen normally), flag as conflict.
        Implements AC-P4-WVR-10: conflicting evidence shows both sources.
        """
        src_set = set(source_evidence)
        tgt_set = set(target_evidence)
        return 1 if src_set & tgt_set else 0

    def record_insight_with_provenance(
        self,
        candidate: InsightCandidate,
        statement: str,
        status: str = "new",
    ) -> int:
        """Persist an insight with full provenance to weaver_insights and weaver_insight_sources.

        Implements:
        - AC-P4-WVR-01: Insight with >=2 sources from 2 projects
        - AC-P4-WVR-02: Candidate from one project only → no insight (handled upstream)
        - AC-P4-WVR-03: Deduplication via evidence_hash
        - AC-P4-WVR-08: No insight text in observations/KG (provenance links only)
        - AC-P4-WVR-09: Staleness tracked via weaver_insight_sources
        - AC-P4-WVR-10: Conflict flag on contradictory evidence
        - AC-P4-WVR-13: Evidence tagged as untrusted source
        """
        # Compute evidence hash for dedup
        evidence_hash = self.compute_evidence_hash(
            candidate.source_evidence, candidate.target_evidence
        )

        # Check for duplicate (AC-P4-WVR-03)
        existing_id = self.check_duplicate_insight(evidence_hash)
        if existing_id is not None:
            return existing_id

        # Detect conflicting evidence (AC-P4-WVR-10)
        conflict_flag = self.detect_conflicting_evidence(
            candidate.source_evidence, candidate.target_evidence
        )

        # Verify we have evidence from BOTH projects (AC-P4-WVR-01, AC-P4-WVR-02)
        if not candidate.source_evidence or not candidate.target_evidence:
            raise WeaverError("Insight requires evidence from both projects")

        now = int(time.time())

        # Start transaction
        cur = self.memory.conn.cursor()

        try:
            # Insert main insight record
            cur.execute(
                """
                INSERT INTO weaver_insights
                (status, source_project, target_project, statement, created_at, updated_at, evidence, evidence_hash, conflict_flag)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    status,
                    candidate.source_project,
                    candidate.target_project,
                    statement,
                    now,
                    now,
                    json.dumps(
                        {
                            "source_evidence": candidate.source_evidence,
                            "target_evidence": candidate.target_evidence,
                        }
                    ),
                    evidence_hash,
                    conflict_flag,
                ),
            )
            insight_id = cur.lastrowid

            # Insert provenance records with hashes and snippets
            all_evidence = candidate.source_evidence + candidate.target_evidence
            obs_hashes = self.get_observation_hashes(all_evidence)

            for obs_id in all_evidence:
                content_hash, snippet = obs_hashes.get(obs_id, ("", ""))
                # Determine which project this observation belongs to
                project = candidate.source_project if obs_id in candidate.source_evidence else candidate.target_project

                # Check if observation source is untrusted (AC-P4-WVR-13)
                cur.execute(
                    "SELECT source FROM observations WHERE id = ?", (obs_id,)
                )
                row = cur.fetchone()
                is_untrusted = 0
                if row and row[0] in ("injected", "untrusted"):
                    is_untrusted = 1

                cur.execute(
                    """
                    INSERT INTO weaver_insight_sources
                    (insight_id, observation_id, project_name, evidence_hash, snippet, is_untrusted, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        insight_id,
                        obs_id,
                        project,
                        content_hash,
                        snippet,
                        is_untrusted,
                        now,
                    ),
                )

            self.memory.conn.commit()
            return insight_id

        except Exception:
            self.memory.conn.rollback()
            raise

    def mark_stale_insights(self) -> int:
        """Scan all non-stale insights and mark stale ones.

        Returns count of insights marked stale.
        Implements AC-P4-WVR-09.
        """
        cur = self.memory.conn.cursor()
        cur.execute(
            "SELECT insight_id FROM weaver_insights WHERE status NOT IN ('stale', 'cancelled')"
        )
        insight_ids = [row[0] for row in cur.fetchall()]

        stale_count = 0
        for insight_id in insight_ids:
            if self.check_staleness(insight_id):
                cur.execute(
                    "UPDATE weaver_insights SET status = 'stale', updated_at = ? WHERE insight_id = ?",
                    (int(time.time()), insight_id),
                )
                stale_count += 1

        if stale_count:
            self.memory.conn.commit()
        return stale_count

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
        """Persist an insight to the weaver_insights table (legacy API)."""
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

    # -----------------------------------------------------------------------
    # C15: Insight Retrieval & Status Management
    # -----------------------------------------------------------------------
    def get_insights(
        self, status_filter: list[str] | None = None, include_stale: bool = False
    ) -> list[CrossProjectInsight]:
        """Fetch insights from weaver_insights table.

        Args:
            status_filter: List of statuses to include. Default: ['new', 'saved'].
            include_stale: If True, also include 'stale' insights.
        """
        if status_filter is None:
            status_filter = ["new", "saved"]

        if include_stale and "stale" not in status_filter:
            status_filter = status_filter + ["stale"]
        elif not include_stale:
            status_filter = [s for s in status_filter if s != "stale"]

        placeholders = ",".join("?" * len(status_filter))
        query = f"""
            SELECT insight_id, status, source_project, target_project, statement,
                   created_at, updated_at, evidence, evidence_hash, conflict_flag
            FROM weaver_insights
            WHERE status IN ({placeholders})
            ORDER BY created_at DESC
        """

        cur = self.memory.conn.cursor()
        cur.execute(query, tuple(status_filter))
        rows = cur.fetchall()

        insights = []
        for row in rows:
            insights.append(
                CrossProjectInsight(
                    insight_id=row[0],
                    status=row[1],
                    source_project=row[2],
                    target_project=row[3],
                    statement=row[4],
                    created_at=row[5],
                    updated_at=row[6],
                    evidence=json.loads(row[7]) if row[7] else {},
                    evidence_hash=row[8],
                    conflict_flag=row[9] or 0,
                )
            )
        return insights

    def get_dismissed_insights(self) -> list[CrossProjectInsight]:
        """Fetch dismissed insights for the Dismissed tab."""
        return self.get_insights(status_filter=["dismissed"], include_stale=True)

    def update_insight_status(self, insight_id: int, new_status: str) -> bool:
        """Update an insight's status (dismiss, save, restore, cancel).

        Args:
            insight_id: The insight to update.
            new_status: One of 'new', 'saved', 'dismissed', 'cancelled'.

        Returns:
            True if updated, False if not found.
        """
        valid_statuses = {"new", "saved", "dismissed", "cancelled", "stale"}
        if new_status not in valid_statuses:
            raise WeaverError(f"Invalid status: {new_status}")

        cur = self.memory.conn.cursor()
        cur.execute(
            "UPDATE weaver_insights SET status = ?, updated_at = ? WHERE insight_id = ?",
            (new_status, int(time.time()), insight_id),
        )
        self.memory.conn.commit()
        return cur.rowcount > 0

    def dismiss_insight(self, insight_id: int) -> bool:
        """Mark an insight as dismissed (moves to Dismissed tab)."""
        return self.update_insight_status(insight_id, "dismissed")

    def save_insight(self, insight_id: int) -> bool:
        """Mark an insight as saved (keeps in active view)."""
        return self.update_insight_status(insight_id, "saved")

    def restore_insight(self, insight_id: int) -> bool:
        """Restore a dismissed insight back to active (new)."""
        return self.update_insight_status(insight_id, "new")

    def cancel_insight(self, insight_id: int) -> bool:
        """Cancel an insight permanently."""
        return self.update_insight_status(insight_id, "cancelled")
