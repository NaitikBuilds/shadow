from shadow.memory import EntityExtractor, GraphBuilder
from shadow.memory import MemoryStore


def make_extractor(projects=None):
    return EntityExtractor(known_projects=projects or [])


def test_extracts_known_project():
    e = make_extractor(["SHADOW"])
    result = e.extract("Working on SHADOW today.")
    kinds = {(r["type"], r["name"]) for r in result}
    assert ("project", "SHADOW") in kinds


def test_extracts_capitalized_topic():
    e = make_extractor()
    result = e.extract("Reading about Visual Studio Code today.")
    names = {r["name"] for r in result if r["type"] == "topic"}
    assert "Visual Studio Code" in names


def test_extracts_filename():
    e = make_extractor()
    result = e.extract("Editing observer.py right now.")
    files = {r["name"] for r in result if r["type"] == "file"}
    assert "observer.py" in files


def test_rejects_stopwords():
    e = make_extractor()
    result = e.extract("The And But If")
    assert result == []


def test_dedupes_repeated_mentions():
    e = make_extractor()
    result = e.extract("SHADOW is great. SHADOW works. SHADOW it is.")
    projects = [r for r in result if r["type"] == "project"]
    assert len(projects) == 0  # no known_projects configured
    topics = [r for r in result if r["name"] == "SHADOW"]
    assert len(topics) == 1


def test_empty_input():
    e = make_extractor()
    assert e.extract("") == []
    assert e.extract("   ") == []


# ---------- GraphBuilder ----------


def test_graph_builder_links_and_edges(tmp_path):
    store = MemoryStore(str(tmp_path / "g.db"), vector_dim=384)
    try:
        extractor = EntityExtractor(known_projects=["SHADOW"])
        builder = GraphBuilder(store, extractor)

        obs_id = store.add_observation(
            "test", "Naitik works on SHADOW using observer.py"
        )
        count = builder.process(obs_id, "Naitik works on SHADOW using observer.py")
        assert count >= 2  # at least Naitik + SHADOW + observer.py

        linked = store.entities_for_observation(obs_id)
        names = {e["name"] for e in linked}
        assert "SHADOW" in names
        assert "observer.py" in names
        assert "Naitik" in names

        # Co-occurrence edge should exist
        shadow = store.entity_by_name("project", "SHADOW")
        naitik = store.entity_by_name("topic", "Naitik")
        # Naitik may come out as topic if not in known_projects
        assert shadow is not None
        # Check that at least one co_occurs edge exists somewhere
        neighbors = store.neighbors(shadow["id"])
        assert len(neighbors) >= 1
    finally:
        store.close()


def test_graph_builder_empty_text(tmp_path):
    store = MemoryStore(str(tmp_path / "g2.db"), vector_dim=384)
    try:
        builder = GraphBuilder(store, EntityExtractor())
        obs_id = store.add_observation("test", "no entities here")
        count = builder.process(obs_id, "no entities here")
        assert count == 0
    finally:
        store.close()
