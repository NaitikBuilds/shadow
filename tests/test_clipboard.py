import time

from shadow.perception import ClipboardSource, PerceptionSource


def test_source_is_perception_source():
    src = ClipboardSource()
    assert isinstance(src, PerceptionSource)


def test_metadata():
    src = ClipboardSource()
    assert src.name == "clipboard"
    assert src.channel == "clipboard"


def test_poll_interval_respected():
    src = ClipboardSource()
    # First call should run (poll time starts at 0)
    # We can't test the clipboard in CI, but we can test the timing logic.
    src._last_poll = time.monotonic()
    # Second call should be throttled
    assert src.sample() is None


def test_secret_patterns_openai_key():
    assert (
        ClipboardSource._looks_like_secret("sk-abcdefghij1234567890abcdefghij") is True
    )


def test_secret_patterns_github_pat():
    assert ClipboardSource._looks_like_secret("ghp_" + "a" * 36) is True


def test_secret_patterns_aws_key():
    assert ClipboardSource._looks_like_secret("AKIAIOSFODNN7EXAMPLE") is True


def test_secret_patterns_pem():
    assert (
        ClipboardSource._looks_like_secret("-----BEGIN RSA PRIVATE KEY-----\nabc")
        is True
    )


def test_secret_patterns_hex():
    assert ClipboardSource._looks_like_secret("a" * 64) is True


def test_secret_patterns_base64():
    assert (
        ClipboardSource._looks_like_secret(
            "YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXo=" + "abcd"
        )
        is True
    )


def test_normal_text_not_secret():
    assert (
        ClipboardSource._looks_like_secret(
            "This is a normal sentence that someone might copy."
        )
        is False
    )


def test_short_text_not_secret():
    assert ClipboardSource._looks_like_secret("hi") is False


def test_url_not_secret():
    assert (
        ClipboardSource._looks_like_secret("https://example.com/some/path?query=1")
        is False
    )
