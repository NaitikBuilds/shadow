import pytest

from shadow.perception import ChangeDetector


def test_defaults():
    d = ChangeDetector()
    info = d.info()
    assert info["threshold"] == 5
    assert info["hash_size"] == 8
    assert info["has_hash"] is False


def test_reset_clears_state():
    d = ChangeDetector()
    d._last_hash = 12345
    d._last_result = False
    d.reset()
    assert d._last_hash is None
    assert d._last_result is True


def test_hamming_distance():
    assert ChangeDetector._hamming(0b0000, 0b0000) == 0
    assert ChangeDetector._hamming(0b0000, 0b1111) == 4
    assert ChangeDetector._hamming(0b1010, 0b0101) == 4
    assert ChangeDetector._hamming(0b1111, 0b1111) == 0


def test_hamming_identical_is_zero():
    d = ChangeDetector()
    assert d._hamming(0xDEADBEEF, 0xDEADBEEF) == 0


def test_dhash_deterministic():
    """Same image produces same hash."""
    pytest.importorskip("PIL")
    from PIL import Image

    d = ChangeDetector()
    img = Image.new("RGB", (100, 100), color=(128, 128, 128))
    h1 = d._dhash(img)
    h2 = d._dhash(img)
    assert h1 == h2


def test_dhash_different_for_different_images():
    pytest.importorskip("PIL")
    from PIL import Image

    d = ChangeDetector()
    img1 = Image.new("RGB", (100, 100), color=(0, 0, 0))
    img2 = Image.new("RGB", (100, 100), color=(255, 255, 255))
    h1 = d._dhash(img1)
    h2 = d._dhash(img2)
    # Solid colors produce equal hashes (no gradient) — but the
    # specific pixel comparisons are all "left > right" = False
    # so both should produce the same all-zeros hash.
    # Verify by using a gradient instead.
    grad1 = Image.new("RGB", (100, 100))
    grad2 = Image.new("RGB", (100, 100))
    for x in range(100):
        for y in range(100):
            grad1.putpixel((x, y), (x * 2, x * 2, x * 2))
            grad2.putpixel((x, y), (255 - x * 2, 255 - x * 2, 255 - x * 2))
    h1 = d._dhash(grad1)
    h2 = d._dhash(grad2)
    assert h1 != h2


def test_dhash_produces_64_bit_int():
    pytest.importorskip("PIL")
    from PIL import Image

    d = ChangeDetector(hash_size=8)
    img = Image.new("RGB", (100, 100), color=(128, 128, 128))
    h = d._dhash(img)
    assert 0 <= h < (1 << 64)


def test_dhash_hash_size_4():
    pytest.importorskip("PIL")
    from PIL import Image

    d = ChangeDetector(hash_size=4)
    img = Image.new("RGB", (100, 100), color=(128, 128, 128))
    h = d._dhash(img)
    # 4x4 = 16 bits
    assert 0 <= h < (1 << 16)


def test_non_windows_returns_changed(monkeypatch):
    import sys

    monkeypatch.setattr(sys, "platform", "linux")
    d = ChangeDetector()
    assert d.has_changed() is True


def test_cached_result_within_interval(monkeypatch):
    """Repeated calls within min_interval_ms return cached result."""
    d = ChangeDetector(min_interval_ms=10000)  # long cache
    # Prime the cache by calling once
    d.has_changed()
    # Manually set last_result and verify caching
    d._last_result = False
    d._last_check_at = __import__("time").monotonic()
    second = d.has_changed()
    # Should return cached False
    assert second is False


def test_capture_failure_returns_changed(monkeypatch):
    d = ChangeDetector()
    monkeypatch.setattr(d, "_capture", lambda bbox: None)
    assert d.has_changed() is True


def test_dhash_failure_returns_changed(monkeypatch):
    pytest.importorskip("PIL")
    from PIL import Image

    d = ChangeDetector()
    img = Image.new("RGB", (10, 10))
    monkeypatch.setattr(d, "_capture", lambda bbox: img)
    monkeypatch.setattr(
        d, "_dhash", lambda i: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    assert d.has_changed() is True


def test_first_call_returns_changed():
    pytest.importorskip("PIL")
    from PIL import Image

    d = ChangeDetector(min_interval_ms=0)
    img = Image.new("RGB", (50, 50), color=(50, 50, 50))
    d._capture = lambda bbox: img
    # First call always returns True (nothing to compare to)
    assert d.has_changed() is True


def test_same_image_returns_unchanged():
    pytest.importorskip("PIL")
    from PIL import Image

    d = ChangeDetector(min_interval_ms=0)
    img = Image.new("RGB", (50, 50))
    # Build a gradient so dhash is meaningful
    for x in range(50):
        for y in range(50):
            img.putpixel((x, y), (x * 5, x * 5, x * 5))

    d._capture = lambda bbox: img
    assert d.has_changed() is True  # first
    assert d.has_changed() is False  # second — same image


def test_different_image_returns_changed():
    pytest.importorskip("PIL")
    from PIL import Image

    d = ChangeDetector(min_interval_ms=0)
    img1 = Image.new("RGB", (50, 50))
    img2 = Image.new("RGB", (50, 50))
    for x in range(50):
        for y in range(50):
            img1.putpixel((x, y), (x * 5, x * 5, x * 5))
            img2.putpixel((x, y), (255 - x * 5, 255 - x * 5, 255 - x * 5))

    d._capture = lambda bbox: img1
    assert d.has_changed() is True  # first

    d._capture = lambda bbox: img2
    # Should be different enough to cross threshold
    assert d.has_changed() is True


def test_info_includes_state():
    d = ChangeDetector()
    info = d.info()
    assert info["threshold"] == 5
    assert info["has_hash"] is False
    d._last_hash = 999
    assert d.info()["has_hash"] is True


def test_config_helper_defaults():
    from shadow.config import change_detection_config

    d = change_detection_config({})
    assert d["enabled"] is True
    assert d["threshold"] == 5
    assert d["hash_size"] == 8


def test_config_helper_overrides():
    from shadow.config import change_detection_config

    cfg = {"perception": {"change_detection": {"threshold": 10}}}
    d = change_detection_config(cfg)
    assert d["threshold"] == 10
    assert d["hash_size"] == 8
