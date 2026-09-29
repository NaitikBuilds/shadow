import tempfile
from pathlib import Path

from shadow.memory import MemoryStore


def test_memory_roundtrip():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = str(Path(tmp) / "test.db")
        store = MemoryStore(db)
        try:
            rid = store.add_observation("test", "hello shadow")
            store.add_embedding(rid, [0.0] * 384)
            store.log_activity("test_action", "details")
            assert len(store.recent_activity()) == 1
            store.wipe()
            assert store.recent_activity() == []
        finally:
            store.close()
