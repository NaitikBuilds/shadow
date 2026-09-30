import dataclasses

import pytest

from shadow.agent import (
    Taint,
    TaintedValue,
    TaintPropagator,
    max_taint,
)


def test_taint_values():
    assert Taint.USER_DIRECT.value == "user_direct"
    assert Taint.DERIVED.value == "derived"
    assert Taint.OBSERVED.value == "observed"


def test_max_taint_returns_strictest():
    assert max_taint(Taint.USER_DIRECT, Taint.DERIVED) == Taint.DERIVED
    assert max_taint(Taint.DERIVED, Taint.OBSERVED) == Taint.OBSERVED
    assert max_taint(Taint.USER_DIRECT, Taint.OBSERVED) == Taint.OBSERVED
    assert max_taint(Taint.USER_DIRECT, Taint.DERIVED, Taint.OBSERVED) == Taint.OBSERVED


def test_max_taint_empty_returns_user_direct():
    assert max_taint() == Taint.USER_DIRECT


def test_from_user_assigns_user_direct():
    p = TaintPropagator()
    tv = p.from_user("hello")
    assert tv.taint == Taint.USER_DIRECT
    assert tv.value == "hello"


def test_from_observation_assigns_observed():
    p = TaintPropagator()
    tv = p.from_observation("content from screen")
    assert tv.taint == Taint.OBSERVED


def test_from_llm_assigns_derived():
    p = TaintPropagator()
    tv = p.from_llm("llm output")
    assert tv.taint == Taint.DERIVED


def test_from_llm_downgrades_to_user_direct_when_verbatim():
    p = TaintPropagator()
    p.remember_user_input("exact string")
    tv = p.from_llm("exact string")
    assert tv.taint == Taint.USER_DIRECT


def test_remember_user_input_ignores_empty():
    p = TaintPropagator()
    p.remember_user_input("")
    p.remember_user_input("   ")
    assert p.is_user_supplied("") is False
    assert p.is_user_supplied("   ") is False


def test_is_user_supplied_matches_stripped():
    p = TaintPropagator()
    p.remember_user_input("  hello world  ")
    assert p.is_user_supplied("hello world") is True
    assert p.is_user_supplied("  hello world  ") is True
    assert p.is_user_supplied("hello") is False


def test_combine_picks_strictest():
    p = TaintPropagator()
    a = p.from_user("a")
    b = p.from_observation("b")
    combined = p.combine(a, b)
    assert combined.taint == Taint.OBSERVED


def test_combine_all_user_direct():
    p = TaintPropagator()
    combined = p.combine(p.from_user("a"), p.from_user("b"))
    assert combined.taint == Taint.USER_DIRECT


def test_combine_empty_returns_user_direct():
    p = TaintPropagator()
    result = p.combine()
    assert result.taint == Taint.USER_DIRECT
    assert result.value == ""


def test_combine_preserves_values():
    p = TaintPropagator()
    a = p.from_user("hello")
    b = p.from_llm("world")
    combined = p.combine(a, b)
    assert "hello" in combined.value
    assert "world" in combined.value


def test_taint_params_labels_all_as_derived():
    p = TaintPropagator()
    result = p.taint_params({"path": "/tmp/x", "mode": "write"})
    assert result["path"].taint == Taint.DERIVED
    assert result["mode"].taint == Taint.DERIVED


def test_taint_params_downgrades_user_supplied():
    p = TaintPropagator()
    p.remember_user_input("/tmp/x")
    result = p.taint_params({"path": "/tmp/x"})
    assert result["path"].taint == Taint.USER_DIRECT


def test_to_plain_strips_taint():
    p = TaintPropagator()
    tainted = p.taint_params({"a": "1", "b": "2"})
    plain = p.to_plain(tainted)
    assert plain == {"a": "1", "b": "2"}


def test_strictest_of_empty():
    assert TaintPropagator.strictest_of({}) == Taint.USER_DIRECT


def test_strictest_of_mixed():
    p = TaintPropagator()
    params = {
        "a": p.from_user("x"),
        "b": p.from_observation("y"),
        "c": p.from_llm("z"),
    }
    assert TaintPropagator.strictest_of(params) == Taint.OBSERVED


def test_tainted_value_is_immutable():
    tv = TaintedValue(value="x", taint=Taint.USER_DIRECT)
    with pytest.raises(dataclasses.FrozenInstanceError):
        tv.value = "y"  # type: ignore


def test_is_untrusted_flags():
    p = TaintPropagator()
    assert p.from_user("x").is_untrusted() is False
    assert p.from_llm("x").is_untrusted() is True
    assert p.from_observation("x").is_untrusted() is True
