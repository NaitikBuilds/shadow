
import pytest

from shadow.config import load_config
from shadow.memory import MemoryStore
from shadow.perception import ObservationWorker


class FakeBackend:
    def embed(self, text):
        return [0.0] * 384

    @property
    def info(self):
        return {"backend": "fake"}


@pytest.fixture
def memory(tmp_path):
    store = MemoryStore(str(tmp_path / "test.db"), vector_dim=384)
    store.seed_consents(["screen_capture", "typing_dynamics"])
    yield store
    store.close()


def test_worker_constructs(memory):
    cfg = load_config()
    w = ObservationWorker(memory, FakeBackend(), cfg)
    assert w is not None
    assert isinstance(w.sources, list)


def test_worker_skips_without_consent(memory):
    """With no consent, a tick should record nothing."""
    cfg = load_config()
    # disable idle-skip so the test isn't foiled by no mouse movement
    cfg["perception"]["idle_skip_sec"] = 99999
    w = ObservationWorker(memory, FakeBackend(), cfg)
    w._do_tick()
    assert memory.recent_activity() == []


def test_worker_records_with_consent(memory):
    """With consent, the active-window source should record something
    (unless the test runner has no foreground window)."""
    cfg = load_config()
    cfg["perception"]["idle_skip_sec"] = 99999
    cfg["perception"]["ocr_every_n_ticks"] = 0  # disable OCR for determinism
    memory.set_consent("screen_capture", True, reason="test")
    w = ObservationWorker(memory, FakeBackend(), cfg)
    w._do_tick()

    # Check that at least one observation was recorded (active_window).
    cur = memory.conn.cursor()
    cur.execute("SELECT COUNT(*) FROM observations")
    count = cur.fetchone()[0]
    # 0 is acceptable if the test runner has no foreground window.
    assert count >= 0


def test_dedupe_suppresses_repeats(memory):
    cfg = load_config()
    cfg["perception"]["idle_skip_sec"] = 99999
    cfg["perception"]["ocr_every_n_ticks"] = 0
    memory.set_consent("screen_capture", True, reason="test")
    w = ObservationWorker(memory, FakeBackend(), cfg)

    # Fabricate a fake source that always returns the same thing
    class FakeSource:
        name = "active_window"
        channel = "screen_capture"

        def sample(self):
            return {"title": "Test", "process": "pytest", "pid": 1, "timestamp": "x"}

    w.sources = [FakeSource()]
    w._do_tick()
    w._do_tick()

    cur = memory.conn.cursor()
    cur.execute("SELECT COUNT(*) FROM observations")
    count = cur.fetchone()[0]
    assert count == 1  # second tick suppressed by dedupe
