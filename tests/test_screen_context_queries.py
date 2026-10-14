from shadow.agent.vision_intents import (
    build_combined_context,
    wants_memory_context,
)

# ---------- wants_memory_context ----------


def test_wants_memory_yesterday():
    assert wants_memory_context("what am I looking at from yesterday?") is True


def test_wants_memory_last_week():
    assert wants_memory_context("how does this relate to last week?") is True


def test_wants_memory_remind():
    assert wants_memory_context("remind me what this file was about") is True


def test_wants_memory_related_to():
    assert wants_memory_context("related to what I read before") is True


def test_wants_memory_what_did_i():
    assert wants_memory_context("what did I write in this file?") is True


def test_wants_memory_how_does_this():
    assert wants_memory_context("how does this connect?") is True


def test_wants_memory_plain_vision_query():
    assert wants_memory_context("describe this") is False


def test_wants_memory_empty():
    assert wants_memory_context("") is False


# ---------- build_combined_context ----------


def test_combined_both_present():
    vision = "[Vision analysis]\na cat"
    memory = "[Relevant past observations]\n- [x] note about cats"
    combined = build_combined_context(vision, memory)
    assert "[Vision analysis]" in combined
    assert "[Relevant past observations]" in combined
    # Vision should come first
    assert combined.index("Vision") < combined.index("Relevant")


def test_combined_only_vision():
    combined = build_combined_context("[Vision]", "")
    assert combined == "[Vision]"


def test_combined_only_memory():
    combined = build_combined_context("", "[Memory]")
    assert combined == "[Memory]"


def test_combined_neither():
    assert build_combined_context("", "") == ""
