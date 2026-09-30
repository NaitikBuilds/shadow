import pytest

from shadow.agent import StyleMirrorEngine, StyleResult
from shadow.memory import MemoryStore


class FakeBackend:
    """Returns canned text and deterministic embeddings."""

    def __init__(self, reply: str = "Generated reply."):
        self.reply = reply
        self.calls = 0

    def generate_stream(self, prompt, max_tokens=256):
        self.calls += 1
        yield self.reply

    def embed(self, text):
        # Simple hash-based vector — same text → same vector
        h = hash(text) & 0xFFFFFFFF
        return [((h >> i) & 0xFF) / 255.0 for i in range(384)]


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "style.db"))
    yield s
    s.close()


def add_document(store, content: str):
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO observations (source, content) VALUES ('document', ?)",
        (content,),
    )
    store.conn.commit()
    return cur.lastrowid


def test_no_samples_returns_low_confidence(store):
    engine = StyleMirrorEngine(store)
    backend = FakeBackend(reply="ok")
    result = engine.generate("say hello", backend)
    assert isinstance(result, StyleResult)
    assert result.sample_count == 0
    assert result.low_confidence is True
    assert result.style_score is None


def test_samples_below_min_chars_skipped(store):
    add_document(store, "short")
    engine = StyleMirrorEngine(store)
    assert engine.sample_style() == []


def test_samples_found_and_used(store):
    for i in range(3):
        add_document(store, "x" * 200 + f" sample {i}")
    engine = StyleMirrorEngine(store)
    samples = engine.sample_style()
    assert len(samples) == 3


def test_document_prefix_stripped(store):
    add_document(store, "Document: notes.md\n" + "y" * 200)
    engine = StyleMirrorEngine(store)
    samples = engine.sample_style()
    assert len(samples) == 1
    assert not samples[0].startswith("Document:")


def test_long_samples_truncated(store):
    add_document(store, "z" * 5000)
    engine = StyleMirrorEngine(store)
    samples = engine.sample_style()
    assert len(samples[0]) <= engine.MAX_SAMPLE_CHARS


def test_generate_uses_samples(store):
    for i in range(3):
        add_document(store, "sample text " * 20 + f" #{i}")
    engine = StyleMirrorEngine(store)
    backend = FakeBackend(reply="Composed reply.")
    result = engine.generate("reply to an email", backend)
    assert result.sample_count == 3
    assert result.text == "Composed reply."
    assert backend.calls == 1


def test_generate_returns_style_result_fields(store):
    add_document(store, "some content " * 20)
    engine = StyleMirrorEngine(store)
    backend = FakeBackend(reply="hi")
    result = engine.generate("test", backend, check_similarity=False)
    assert hasattr(result, "text")
    assert hasattr(result, "style_score")
    assert hasattr(result, "sample_count")
    assert hasattr(result, "low_confidence")


def test_similarity_returns_float(store):
    add_document(store, "abc " * 50)
    engine = StyleMirrorEngine(store)
    backend = FakeBackend()
    score = engine._similarity("test", ["sample"], backend)
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_similarity_handles_empty_text(store):
    engine = StyleMirrorEngine(store)
    backend = FakeBackend()
    assert engine._similarity("", ["sample"], backend) == 0.0


def test_style_prompt_includes_examples(store):
    engine = StyleMirrorEngine(store)
    prompt = engine._build_style_prompt("do the thing", ["ex1", "ex2"])
    assert "Example 1" in prompt
    assert "Example 2" in prompt
    assert "do the thing" in prompt
    assert "Match tone" in prompt
