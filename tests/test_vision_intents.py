
from shadow.agent import (
    VisionIntent,
    build_vision_context,
    detect_intent,
)
from shadow.hal import TASK_CAPTION, TASK_OCR, TASK_QUERY

# ---------- intent detection ----------


def test_describe_screen_what_am_i_looking_at():
    i = detect_intent("what am I looking at?")
    assert i is not None
    assert i.kind == "describe_screen"
    assert i.task == TASK_CAPTION


def test_describe_screen_variants():
    for q in (
        "describe this",
        "what's on my screen",
        "what is on the screen",
        "what am I seeing",
    ):
        assert detect_intent(q) is not None, q


def test_explain_error_detected():
    i = detect_intent("can you explain this error?")
    assert i is not None
    assert i.kind == "explain_error"
    assert i.task == TASK_QUERY
    assert "error" in i.prompt.lower()


def test_explain_error_variants():
    for q in (
        "explain the error",
        "what does this error mean",
        "help me debug this error",
        "why does this fail",
    ):
        i = detect_intent(q)
        assert i is not None, q
        assert i.kind == "explain_error"


def test_summarize_page_detected():
    i = detect_intent("summarize this page")
    assert i is not None
    assert i.kind == "summarize_page"
    assert i.task == TASK_QUERY
    assert "summarize" in i.prompt.lower()


def test_extract_text_detected():
    i = detect_intent("what does this say?")
    assert i is not None
    assert i.kind == "extract_text"
    assert i.task == TASK_OCR


def test_extract_text_variants():
    for q in (
        "read this",
        "extract the text",
        "read what I'm looking at",
    ):
        i = detect_intent(q)
        assert i is not None, q
        assert i.kind == "extract_text"


def test_case_insensitive():
    assert detect_intent("WHAT AM I LOOKING AT") is not None
    assert detect_intent("Explain This Error") is not None


def test_normal_query_returns_none():
    assert detect_intent("what is a knowledge graph?") is None
    assert detect_intent("remind me to call mom") is None
    assert detect_intent("hello") is None


def test_empty_query_returns_none():
    assert detect_intent("") is None
    assert detect_intent("   ") is None


def test_matched_phrase_recorded():
    i = detect_intent("hey, what am I looking at?")
    assert i is not None
    assert i.matched_phrase.lower().startswith("what am i")


def test_intent_to_dict():
    i = detect_intent("describe this")
    assert i is not None
    d = i.to_dict()
    assert d["kind"] == "describe_screen"
    assert d["task"] == TASK_CAPTION
    assert "matched_phrase" in d


# ---------- context building ----------


def test_build_context_with_result():
    intent = VisionIntent(
        kind="describe_screen",
        task=TASK_CAPTION,
        prompt="",
        matched_phrase="describe this",
    )
    result = {
        "text": "a code editor window",
        "window_title": "recovery.py — VS Code",
        "process": "Code.exe",
    }
    context = build_vision_context(intent, result)
    assert "Vision analysis" in context
    assert "recovery.py" in context
    assert "Code.exe" in context
    assert "a code editor window" in context


def test_build_context_without_result():
    intent = VisionIntent(
        kind="describe_screen",
        task=TASK_CAPTION,
        prompt="",
        matched_phrase="describe this",
    )
    context = build_vision_context(intent, None)
    assert "no image was available" in context.lower()


def test_build_context_handles_empty_text():
    intent = VisionIntent(
        kind="describe_screen",
        task=TASK_CAPTION,
        prompt="",
        matched_phrase="describe this",
    )
    result = {"text": "", "window_title": "", "process": ""}
    context = build_vision_context(intent, result)
    assert "Vision analysis" in context
    assert "(empty)" in context
