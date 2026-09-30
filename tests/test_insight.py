from shadow.agent import Insight


def test_insight_defaults():
    i = Insight(kind="recovery", title="Test", body="Body")
    assert i.score == 0.5
    assert i.action == ""
    assert i.entity_id is None
    assert i.created_at


def test_insight_to_dict():
    i = Insight(
        kind="recovery",
        title="Unfinished: SHADOW",
        body="Worked for 30 min.",
        score=0.8,
        action="Resume",
        entity_id=42,
    )
    d = i.to_dict()
    assert d["kind"] == "recovery"
    assert d["score"] == 0.8
    assert d["entity_id"] == 42
    assert set(d.keys()) == {
        "kind",
        "title",
        "body",
        "score",
        "action",
        "entity_id",
        "created_at",
    }
