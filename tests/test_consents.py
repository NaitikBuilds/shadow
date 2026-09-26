import tempfile
from pathlib import Path

from shadow.memory import MemoryStore


def test_consent_seed_and_toggle():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = str(Path(tmp) / "test.db")
        store = MemoryStore(db)
        try:
            store.seed_consents(["screen_capture", "typing_dynamics"])
            assert store.get_consent("screen_capture") is False

            store.set_consent("screen_capture", True, reason="user enabled in panel")
            assert store.get_consent("screen_capture") is True
            assert store.get_consent("typing_dynamics") is False

            audit = store.consent_audit()
            assert audit[0][1] == "screen_capture"
            assert audit[0][2] == "enable"

            store.set_consent("screen_capture", False, reason="user disabled")
            assert store.get_consent("screen_capture") is False
            assert len(store.consent_audit()) == 2

            allc = store.all_consents()
            assert allc == {"screen_capture": False, "typing_dynamics": False}
        finally:
            store.close()