from shadow.perception import (
    WindowCategory,
    WindowClassifier,
)


def test_browser_detected():
    c = WindowClassifier()
    profile = c.classify("chrome.exe", "GitHub — chrome")
    assert profile.category == WindowCategory.BROWSER
    assert profile.use_uia is True
    assert profile.use_ocr is True
    assert profile.extract_url is True


def test_edge_detected():
    c = WindowClassifier()
    profile = c.classify("msedge.exe", "Docs")
    assert profile.category == WindowCategory.BROWSER


def test_vscode_is_editor():
    c = WindowClassifier()
    profile = c.classify("Code.exe", "recovery.py — shadow — VS Code")
    assert profile.category == WindowCategory.EDITOR
    assert profile.extract_path is True
    assert profile.extract_url is False
    assert profile.use_ocr is False


def test_visual_studio_is_editor():
    c = WindowClassifier()
    profile = c.classify("devenv.exe", "Solution Explorer")
    assert profile.category == WindowCategory.EDITOR


def test_terminal_uses_ocr_only():
    c = WindowClassifier()
    profile = c.classify("WindowsTerminal.exe", "Windows PowerShell")
    assert profile.category == WindowCategory.TERMINAL
    assert profile.use_uia is False
    assert profile.use_ocr is True


def test_powershell_is_terminal():
    c = WindowClassifier()
    profile = c.classify("powershell.exe", "PowerShell")
    assert profile.category == WindowCategory.TERMINAL


def test_word_is_document():
    c = WindowClassifier()
    profile = c.classify("WINWORD.EXE", "Report.docx")
    assert profile.category == WindowCategory.DOCUMENT
    assert profile.use_uia is True


def test_pdf_reader_is_document():
    c = WindowClassifier()
    profile = c.classify("AcroRd32.exe", "paper.pdf")
    assert profile.category == WindowCategory.DOCUMENT


def test_slack_is_chat():
    c = WindowClassifier()
    profile = c.classify("slack.exe", "#engineering")
    assert profile.category == WindowCategory.CHAT


def test_teams_is_chat():
    c = WindowClassifier()
    profile = c.classify("ms-teams.exe", "Meeting with Priya")
    assert profile.category == WindowCategory.CHAT


def test_spotify_is_media():
    c = WindowClassifier()
    profile = c.classify("Spotify.exe", "Song name")
    assert profile.category == WindowCategory.MEDIA
    # Media apps don't get text extraction
    assert profile.use_uia is False
    assert profile.use_ocr is False


def test_vlc_is_media():
    c = WindowClassifier()
    profile = c.classify("vlc.exe", "video.mp4")
    assert profile.category == WindowCategory.MEDIA


def test_obsidian_is_notes():
    c = WindowClassifier()
    profile = c.classify("Obsidian.exe", "My Vault")
    assert profile.category == WindowCategory.NOTES
    assert profile.use_uia is True


def test_notion_is_notes():
    c = WindowClassifier()
    profile = c.classify("Notion.exe", "Project notes")
    assert profile.category == WindowCategory.NOTES


def test_unknown_app_is_other():
    c = WindowClassifier()
    profile = c.classify("some_random_app.exe", "Random window")
    assert profile.category == WindowCategory.OTHER
    # Conservative default: both enabled
    assert profile.use_uia is True
    assert profile.use_ocr is True


def test_self_observation_detected_by_title():
    c = WindowClassifier()
    profile = c.classify(
        "python.exe",
        "SHADOW — Silent On-Device Life Context Agent",
    )
    assert profile.is_self is True
    assert profile.use_uia is False
    assert profile.use_ocr is False


def test_self_observation_not_flagged_for_other_python():
    c = WindowClassifier()
    profile = c.classify("python.exe", "Some Other Python App")
    assert profile.is_self is False


def test_custom_map_override():
    c = WindowClassifier(custom_map={"my_tool": "editor"})
    profile = c.classify("my_tool.exe", "Custom")
    assert profile.category == WindowCategory.EDITOR


def test_custom_map_invalid_value_ignored():
    c = WindowClassifier(custom_map={"foo": "invalid_category"})
    profile = c.classify("foo.exe", "test")
    # Falls through to OTHER
    assert profile.category == WindowCategory.OTHER


def test_process_name_without_exe():
    c = WindowClassifier()
    profile = c.classify("chrome", "GitHub")
    assert profile.category == WindowCategory.BROWSER


def test_process_case_insensitive():
    c = WindowClassifier()
    profile = c.classify("CHROME.EXE", "GitHub")
    assert profile.category == WindowCategory.BROWSER


def test_extract_url_from_title():
    url = WindowClassifier.extract_url_from_title(
        "Docs — https://docs.python.org/3/ — Chrome"
    )
    assert url == "https://docs.python.org/3/"


def test_extract_url_from_title_none():
    assert WindowClassifier.extract_url_from_title("Plain title") is None


def test_extract_path_from_title():
    path = WindowClassifier.extract_path_from_title(
        "recovery.py — shadow — Visual Studio Code"
    )
    assert path == "recovery.py"


def test_extract_path_from_title_with_dash():
    path = WindowClassifier.extract_path_from_title("main.py - project - Code")
    assert path == "main.py"


def test_extract_path_from_title_none():
    assert WindowClassifier.extract_path_from_title("No file here") is None


def test_profile_to_dict_serializable():
    c = WindowClassifier()
    profile = c.classify("chrome.exe", "GitHub — Chrome")
    d = profile.to_dict()
    assert d["category"] == "browser"
    assert d["process"] == "chrome"
    assert d["extract_url"] is True
    assert isinstance(d["notes"], list)


def test_empty_process_name():
    c = WindowClassifier()
    profile = c.classify("", "")
    assert profile.category == WindowCategory.OTHER
    assert profile.is_self is False


def test_config_helper_defaults():
    from shadow.config import window_classifier_config

    d = window_classifier_config({})
    assert d["custom_map"] == {}


def test_config_helper_overrides():
    from shadow.config import window_classifier_config

    cfg = {"perception": {"window_classifier": {"custom_map": {"x": "editor"}}}}
    d = window_classifier_config(cfg)
    assert d["custom_map"]["x"] == "editor"
