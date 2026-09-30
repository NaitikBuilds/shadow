"""Taint propagation for action parameters.

Every action parameter carries a trust label:
  - user_direct : value came verbatim from a user-typed input
  - derived     : value was synthesized by the LLM
  - observed    : value could have been influenced by observed content

Strictness ordering (highest to lowest):
  observed > derived > user_direct

The Permission Engine (Phase 4.5a) uses these labels together with the
action's risk tier to decide auto-run / confirm / double-confirm.

Design: this module only *assigns* taint. It never mutates labels once
set. Callers that combine values must use the stricter of the inputs.
"""

from dataclasses import dataclass
from enum import StrEnum


class Taint(StrEnum):
    USER_DIRECT = "user_direct"
    DERIVED = "derived"
    OBSERVED = "observed"


# Strictness ranking: higher = stricter.
_RANK = {
    Taint.USER_DIRECT: 0,
    Taint.DERIVED: 1,
    Taint.OBSERVED: 2,
}


def max_taint(*taints: Taint) -> Taint:
    """Return the strictest taint among the inputs."""
    if not taints:
        return Taint.USER_DIRECT
    return max(taints, key=lambda t: _RANK[t])


@dataclass(frozen=True)
class TaintedValue:
    """A value plus its trust label.

    Immutable by design — assign once at construction. To combine
    several tainted inputs, use TaintPropagator.combine().
    """

    value: str
    taint: Taint

    def is_untrusted(self) -> bool:
        return self.taint in (Taint.OBSERVED, Taint.DERIVED)


class TaintPropagator:
    """Assigns and combines taint labels for action parameters."""

    def __init__(self):
        # Values explicitly typed by the user in this session.
        self._user_values: set[str] = set()

    # ---------- user input registration ----------

    def remember_user_input(self, text: str) -> None:
        """Record a string the user typed in this session.

        Any parameter that matches this string verbatim can be
        labelled USER_DIRECT instead of DERIVED.
        """
        cleaned = (text or "").strip()
        if cleaned:
            self._user_values.add(cleaned)

    def is_user_supplied(self, value: str) -> bool:
        return (value or "").strip() in self._user_values

    # ---------- assignment ----------

    def from_user(self, value: str) -> TaintedValue:
        """Assign the lowest taint. Use only when the caller is certain
        the value came from a user-typed input."""
        return TaintedValue(value=str(value), taint=Taint.USER_DIRECT)

    def from_observation(self, value: str) -> TaintedValue:
        """Assign OBSERVED taint."""
        return TaintedValue(value=str(value), taint=Taint.OBSERVED)

    def from_llm(self, value: str) -> TaintedValue:
        """Assign DERIVED taint.

        If the value matches a user-typed string verbatim, downgrade
        to USER_DIRECT.
        """
        cleaned = str(value).strip()
        if self.is_user_supplied(cleaned):
            return TaintedValue(value=str(value), taint=Taint.USER_DIRECT)
        return TaintedValue(value=str(value), taint=Taint.DERIVED)

    def combine(self, *values: TaintedValue) -> TaintedValue:
        """Combine several tainted values into one.

        The result carries the strictest input taint. The value is the
        string-joined content of all inputs (preserves readability).
        """
        if not values:
            return TaintedValue(value="", taint=Taint.USER_DIRECT)

        strictest = max_taint(*(v.taint for v in values))
        joined = " ".join(v.value for v in values if v.value)
        return TaintedValue(value=joined, taint=strictest)

    # ---------- parameter dict helpers ----------

    def taint_params(self, params: dict[str, str]) -> dict[str, TaintedValue]:
        """Label every value in a params dict as DERIVED (conservative).

        Caller can override individual entries with from_user() or
        from_observation() when the source is known.
        """
        return {k: self.from_llm(str(v)) for k, v in params.items()}

    @staticmethod
    def to_plain(params: dict[str, TaintedValue]) -> dict[str, str]:
        """Strip taint labels for execution."""
        return {k: v.value for k, v in params.items()}

    @staticmethod
    def strictest_of(params: dict[str, TaintedValue]) -> Taint:
        """Return the strictest taint across all parameter values."""
        if not params:
            return Taint.USER_DIRECT
        return max_taint(*(v.taint for v in params.values()))
