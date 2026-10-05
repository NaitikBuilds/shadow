
from shadow.perception import AdaptiveCadence, CadenceInfo


class FakeDetector:
    """Returns canned change signals in sequence."""

    def __init__(self, sequence: list[bool] | None = None):
        self.sequence = list(sequence or [])
        self.calls = 0

    def has_changed(self) -> bool:
        self.calls += 1
        if not self.sequence:
            return False
        return self.sequence.pop(0)


def cfg(enabled=True):
    return {
        "perception": {
            "cadence": {
                "enabled": enabled,
                "min_interval_sec": 5,
                "max_interval_sec": 60,
                "idle_interval_sec": 30,
                "accelerate_multiplier": 0.5,
                "backoff_multiplier": 1.5,
            }
        }
    }


def test_initial_interval_is_idle():
    c = AdaptiveCadence(FakeDetector(), cfg())
    assert c.current_interval == 30


def test_changed_shrinks_interval():
    c = AdaptiveCadence(FakeDetector([True]), cfg())
    changed, next_interval = c.sample()
    assert changed is True
    # 30 * 0.5 = 15
    assert next_interval == 15


def test_unchanged_grows_interval():
    c = AdaptiveCadence(FakeDetector([False]), cfg())
    changed, next_interval = c.sample()
    assert changed is False
    # 30 * 1.5 = 45
    assert next_interval == 45


def test_repeated_changes_hit_min():
    c = AdaptiveCadence(FakeDetector([True] * 20), cfg())
    for _ in range(20):
        c.sample()
    assert c.current_interval == 5  # min clamp


def test_repeated_unchanged_hits_max():
    c = AdaptiveCadence(FakeDetector([False] * 20), cfg())
    for _ in range(20):
        c.sample()
    assert c.current_interval == 60  # max clamp


def test_mixed_sequence_oscillates():
    c = AdaptiveCadence(FakeDetector([True, True, False, False]), cfg())
    c.sample()  # 30 -> 15
    assert c.current_interval == 15
    c.sample()  # 15 -> 7 (int)
    assert c.current_interval == 7
    c.sample()  # 7 -> 10 (int of 7*1.5)
    assert c.current_interval == 10
    c.sample()  # 10 -> 15
    assert c.current_interval == 15


def test_due_false_immediately():
    c = AdaptiveCadence(FakeDetector(), cfg())
    # Never sampled, last_sample_at = 0, so due() returns True
    # unless the interval is huge
    c._last_sample_at = __import__("time").monotonic()
    assert c.due() is False


def test_due_true_when_disabled():
    c = AdaptiveCadence(FakeDetector(), cfg(enabled=False))
    assert c.due() is True


def test_sample_when_disabled_no_change():
    c = AdaptiveCadence(FakeDetector([True]), cfg(enabled=False))
    changed, interval = c.sample()
    assert changed is False
    assert interval == c.idle_interval


def test_reset_restores_idle():
    c = AdaptiveCadence(FakeDetector([True] * 5), cfg())
    for _ in range(5):
        c.sample()
    assert c.current_interval == 5
    c.reset()
    assert c.current_interval == 30
    assert c.info().total_samples == 0
    assert c.info().changed_count == 0


def test_info_tracks_counts():
    c = AdaptiveCadence(FakeDetector([True, False, True]), cfg())
    c.sample()
    c.sample()
    c.sample()
    info = c.info()
    assert isinstance(info, CadenceInfo)
    assert info.total_samples == 3
    assert info.changed_count == 2
    assert info.last_changed is True


def test_last_changed_reflects_latest():
    c = AdaptiveCadence(FakeDetector([True, False]), cfg())
    c.sample()
    assert c.last_changed is True
    c.sample()
    assert c.last_changed is False


def test_no_detector_call_when_disabled():
    detector = FakeDetector([True])
    c = AdaptiveCadence(detector, cfg(enabled=False))
    c.sample()
    assert detector.calls == 0


def test_config_helper_defaults():
    from shadow.config import cadence_config

    d = cadence_config({})
    assert d["enabled"] is True
    assert d["min_interval_sec"] == 5
    assert d["max_interval_sec"] == 60
    assert d["idle_interval_sec"] == 30


def test_config_helper_overrides():
    from shadow.config import cadence_config

    cfg_override = {"perception": {"cadence": {"min_interval_sec": 2}}}
    d = cadence_config(cfg_override)
    assert d["min_interval_sec"] == 2
    assert d["max_interval_sec"] == 60
