from shadow.agent import (
    THIN_TEXT_THRESHOLD_CHARS,
    VISUAL_CATEGORIES,
    VisionOfferPolicy,
)


def test_constants_present():
    assert THIN_TEXT_THRESHOLD_CHARS == 200
    assert "browser" in VISUAL_CATEGORIES
    assert "document" in VISUAL_CATEGORIES
    assert "terminal" not in VISUAL_CATEGORIES


def test_disabled_policy_never_offers():
    policy = VisionOfferPolicy(enabled=False)
    assert policy.should_offer("chrome.exe", "browser") is False


def test_first_offer_allowed_for_browser():
    policy = VisionOfferPolicy()
    assert policy.should_offer("chrome.exe", "browser") is True


def test_editor_category_not_offered():
    policy = VisionOfferPolicy()
    assert policy.should_offer("Code.exe", "editor") is False


def test_terminal_category_not_offered():
    policy = VisionOfferPolicy()
    assert policy.should_offer("WindowsTerminal.exe", "terminal") is False


def test_media_category_not_offered():
    policy = VisionOfferPolicy()
    assert policy.should_offer("Spotify.exe", "media") is False


def test_notes_category_offered():
    policy = VisionOfferPolicy()
    assert policy.should_offer("Obsidian.exe", "notes") is True


def test_empty_process_not_offered():
    policy = VisionOfferPolicy()
    assert policy.should_offer("", "browser") is False


def test_record_yes_sets_cooldown():
    policy = VisionOfferPolicy(cooldown_min=15)
    policy.record("chrome.exe", "yes")
    assert policy.should_offer("chrome.exe", "browser") is False


def test_record_not_now_sets_cooldown():
    policy = VisionOfferPolicy(cooldown_min=15)
    policy.record("chrome.exe", "not_now")
    assert policy.should_offer("chrome.exe", "browser") is False


def test_record_never_excludes_when_store_attached(tmp_path):
    from shadow.memory import MemoryStore, VisionExclusionStore

    store = MemoryStore(str(tmp_path / "excl.db"))
    try:
        exclusions = VisionExclusionStore(store)
        policy = VisionOfferPolicy(cooldown_min=15, exclusions=exclusions)
        policy.record("chrome.exe", "never")
        assert policy.should_offer("chrome.exe", "browser") is False
        assert policy.is_excluded("chrome.exe") is True
    finally:
        store.close()


def test_normalization_case_insensitive():
    policy = VisionOfferPolicy()
    policy.record("Chrome.EXE", "never")
    assert policy.is_excluded("chrome.exe") is True


def test_normalization_strips_exe():
    policy = VisionOfferPolicy()
    policy.record("Code.exe", "never")
    assert policy.is_excluded("code") is True


def test_excluded_process_list(tmp_path):
    from shadow.memory import MemoryStore, VisionExclusionStore

    store = MemoryStore(str(tmp_path / "excl.db"))
    try:
        exclusions = VisionExclusionStore(store)
        policy = VisionOfferPolicy(exclusions=exclusions)
        policy.record("chrome.exe", "never")
        policy.record("firefox.exe", "never")
        excluded = policy.excluded_processes()
        assert "chrome" in excluded
        assert "firefox" in excluded
        assert len(excluded) == 2
    finally:
        store.close()


def test_clear_exclusions(tmp_path):
    from shadow.memory import MemoryStore, VisionExclusionStore

    store = MemoryStore(str(tmp_path / "excl.db"))
    try:
        exclusions = VisionExclusionStore(store)
        policy = VisionOfferPolicy(exclusions=exclusions)
        policy.record("chrome.exe", "never")
        policy.clear_exclusions()
        assert policy.excluded_processes() == set()
        assert policy.should_offer("chrome.exe", "browser") is True
    finally:
        store.close()


def test_seconds_until_ready_fresh_process():
    policy = VisionOfferPolicy(cooldown_min=15)
    # Fresh process — should be ready immediately
    assert policy.seconds_until_ready("chrome.exe") == 0


def test_seconds_until_ready_after_choice():
    policy = VisionOfferPolicy(cooldown_min=15)
    policy.record("chrome.exe", "yes")
    remaining = policy.seconds_until_ready("chrome.exe")
    assert 0 < remaining <= 15 * 60


def test_seconds_until_ready_excluded_returns_negative(tmp_path):
    from shadow.memory import MemoryStore, VisionExclusionStore

    store = MemoryStore(str(tmp_path / "excl.db"))
    try:
        exclusions = VisionExclusionStore(store)
        policy = VisionOfferPolicy(exclusions=exclusions)
        policy.record("chrome.exe", "never")
        assert policy.seconds_until_ready("chrome.exe") == -1
    finally:
        store.close()
