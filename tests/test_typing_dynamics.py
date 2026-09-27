import time

from shadow.perception import PerceptionSource, TypingDynamicsSource


def test_source_is_perception_source():
    src = TypingDynamicsSource()
    try:
        assert isinstance(src, PerceptionSource)
    finally:
        src.stop()


def test_metadata():
    src = TypingDynamicsSource()
    try:
        assert src.name == "typing_dynamics"
        assert src.channel == "typing_dynamics"
    finally:
        src.stop()


def test_sample_returns_none_when_empty():
    src = TypingDynamicsSource()
    try:
        # No keys typed in the test session
        assert src.sample() is None
    finally:
        src.stop()


def test_focus_score_bounds():
    # Steady moderate typing should score mid-high
    s = TypingDynamicsSource._focus_score(60.0, 1.0, 0)
    assert 0.0 <= s <= 1.0
    assert s > 0.7

    # Very slow typing scores low
    s_slow = TypingDynamicsSource._focus_score(2.0, 0.5, 0)
    assert s_slow < 0.5

    # Fast typing with many pauses scores lower than steady
    s_fast_pauses = TypingDynamicsSource._focus_score(150.0, 0.1, 5)
    assert s_fast_pauses < 0.7


def test_sample_after_synthetic_events():
    """Inject events manually to avoid depending on real keyboard input."""
    src = TypingDynamicsSource()
    try:
        base = time.monotonic()
        with src._lock:
            src._events = [base + i * 0.15 for i in range(30)]
        result = src.sample()
        assert result is not None
        assert result["keystrokes"] == 30
        assert result["kpm"] > 0
        assert "summary" in result
        assert "Typing activity" in result["summary"]
    finally:
        src.stop()


def test_sample_below_min_keystrokes():
    src = TypingDynamicsSource()
    try:
        base = time.monotonic()
        with src._lock:
            src._events = [base, base + 0.1, base + 0.2]  # only 3 events
        assert src.sample() is None
    finally:
        src.stop()


def test_sample_resets_window():
    src = TypingDynamicsSource()
    try:
        base = time.monotonic()
        with src._lock:
            src._events = [base + i * 0.1 for i in range(20)]
        first = src.sample()
        assert first is not None
        # Second call has no new events
        second = src.sample()
        assert second is None
    finally:
        src.stop()
