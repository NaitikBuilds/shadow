"""Tests for C12: promotion flow."""

from __future__ import annotations

import pytest

from shadow.agent.shadow_cloning import (
    CloneManager,
    DuplicatePromotionError,
)
from shadow.memory import MemoryStore

pytestmark = pytest.mark.p4


class FakeEmbedBackend:
    def __init__(self, vec_dim: int = 384) -> None:
        self.vec_dim = vec_dim
        self.calls: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        return [0.0] * self.vec_dim


@pytest.fixture
def memory(tmp_path):
    s = MemoryStore(str(tmp_path / "test.db"))
    yield s
    s.close()


@pytest.fixture
def manager(memory):
    return CloneManager(memory, config={"clone_max_concurrent": 2})


@pytest.fixture
def session(manager):
    return manager.create(
        "promo-test",
        {"time_range": {"start": "2026-01-01 00:00:00", "end": "2026-12-31 23:59:59"}},
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------
def test_promote_creates_observation(session, memory):
    art = session.add_artifact("sim output one")
    note_ref = session.promote(art["artifact_id"])
    assert note_ref > 0
    row = memory.conn.execute(
        "SELECT source, content FROM observations WHERE id = ?",
        (note_ref,),
    ).fetchone()
    assert row == ("shadow_clone_promote", "sim output one")


def test_promote_records_clone_promotion(session, memory):
    art = session.add_artifact("promotable")
    session.promote(art["artifact_id"])
    row = memory.conn.execute(
        "SELECT clone_id, artifact_id, content_hash, note_ref "
        "FROM clone_promotions WHERE artifact_id = ?",
        (art["artifact_id"],),
    ).fetchone()
    assert row is not None
    assert row[0] == session.clone_id
    assert row[2] == art["content_hash"]
    assert row[3] > 0


def test_promote_stores_provenance_in_metadata(session, memory):
    art = session.add_artifact("sim")
    note_ref = session.promote(art["artifact_id"])
    row = memory.conn.execute(
        "SELECT metadata FROM observations WHERE id = ?",
        (note_ref,),
    ).fetchone()
    import json

    prov = json.loads(row[0])
    assert prov["promoted_from"] == "shadow_clone"
    assert prov["clone_id"] == session.clone_id
    assert prov["artifact_id"] == art["artifact_id"]


def test_promote_note_searchable(session, memory):
    art = session.add_artifact("UniqueMarkerPhraseFromClone")
    session.promote(art["artifact_id"])
    hits = memory.search_observations(query="UniqueMarkerPhraseFromClone")
    assert any(r[3] == "UniqueMarkerPhraseFromClone" for r in hits)


def test_promote_with_backend_adds_embedding(session, memory):
    backend = FakeEmbedBackend()
    art = session.add_artifact("embeddable")
    note_ref = session.promote(art["artifact_id"], backend=backend)
    assert backend.calls == ["embeddable"]
    cnt = memory.conn.execute(
        "SELECT COUNT(*) FROM vec_observations WHERE rowid = ?",
        (note_ref,),
    ).fetchone()[0]
    assert cnt == 1


def test_promote_without_backend_no_embedding(session, memory):
    art = session.add_artifact("embeddable")
    note_ref = session.promote(art["artifact_id"])
    cnt = memory.conn.execute(
        "SELECT COUNT(*) FROM vec_observations WHERE rowid = ?",
        (note_ref,),
    ).fetchone()[0]
    assert cnt == 0


def test_promote_backend_failure_still_saves_note(session, memory):
    class BoomEmbed:
        def embed(self, _t):
            raise RuntimeError("no vec")

    art = session.add_artifact("survives")
    note_ref = session.promote(art["artifact_id"], backend=BoomEmbed())
    row = memory.conn.execute(
        "SELECT content FROM observations WHERE id = ?",
        (note_ref,),
    ).fetchone()
    assert row == ("survives",)


# ---------------------------------------------------------------------------
# Duplicate rejection (CLN-05)
# ---------------------------------------------------------------------------
def test_promote_rejects_same_artifact_twice(session):
    art = session.add_artifact("dup")
    session.promote(art["artifact_id"])
    with pytest.raises(DuplicatePromotionError):
        session.promote(art["artifact_id"])


def test_promote_rejects_duplicate_content_hash(session, manager):
    art1 = session.add_artifact("same text")
    session.promote(art1["artifact_id"])
    # New session, new artifact, same content -> same hash -> rejected
    s2 = manager.create(
        "other",
        {"time_range": {"start": "2026-01-01 00:00:00"}},
    )
    art2 = s2.add_artifact("same text")
    with pytest.raises(DuplicatePromotionError):
        s2.promote(art2["artifact_id"])


def test_promote_allows_different_hashes(session):
    a1 = session.add_artifact("one")
    a2 = session.add_artifact("two")
    session.promote(a1["artifact_id"])
    session.promote(a2["artifact_id"])  # no raise


# ---------------------------------------------------------------------------
# Precondition failures
# ---------------------------------------------------------------------------
def test_promote_unknown_artifact_raises(session):
    with pytest.raises(ValueError):
        session.promote("does-not-exist")


def test_promote_inactive_session_raises(session):
    art = session.add_artifact("x")
    session.discard()
    with pytest.raises(RuntimeError):
        session.promote(art["artifact_id"])


# ---------------------------------------------------------------------------
# Isolation guarantees (CLN-01/CLN-13)
# ---------------------------------------------------------------------------
def test_promote_only_promotes_selected(session, memory):
    before = memory.conn.execute(
        "SELECT COUNT(*) FROM observations WHERE source='shadow_clone_promote'"
    ).fetchone()[0]
    a1 = session.add_artifact("keep")
    session.add_artifact("drop")
    session.promote(a1["artifact_id"])
    after = memory.conn.execute(
        "SELECT COUNT(*) FROM observations WHERE source='shadow_clone_promote'"
    ).fetchone()[0]
    assert after - before == 1


def test_promote_visible_to_next_clone(session, manager):
    art = session.add_artifact("shared memory")
    session.promote(art["artifact_id"])
    s2 = manager.create("reader", {"time_range": {"start": "2026-01-01 00:00:00"}})
    hits = s2.facade.search_observations(query="shared memory")
    assert any(r[3] == "shared memory" for r in hits)


# ---------------------------------------------------------------------------
# End-to-end (CLN-13)
# ---------------------------------------------------------------------------
def test_promote_discard_end_to_end(session, memory, manager):
    art = session.add_artifact("the chosen one")
    note_ref = session.promote(art["artifact_id"])
    manager.discard(session.clone_id)

    # Promoted note survives
    row = memory.conn.execute(
        "SELECT content FROM observations WHERE id = ?",
        (note_ref,),
    ).fetchone()
    assert row == ("the chosen one",)

    # Clone bookkeeping is now discarded
    row = memory.conn.execute(
        "SELECT status FROM clone_sessions WHERE clone_id = ?",
        (session.clone_id,),
    ).fetchone()
    assert row[0] == "discarded"
