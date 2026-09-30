"""Verify that all engines use UTC consistently.

Regression test for a bug where engines used datetime.now() (local time)
while observations were stored in UTC, causing every comparison to be
off by the local UTC offset.
"""

import inspect
import sys

from shadow.agent import (
    ClipboardActionsEngine,
    ForecastingEngine,
    KnowledgeDecayEngine,
    RecoveryEngine,
)


def _module_source(cls) -> str:
    """Return the source of the module the class lives in."""
    module_name = cls.__module__
    module = sys.modules.get(module_name)
    if module is None:
        return ""
    return inspect.getsource(module)


def test_recovery_uses_utc():
    src = _module_source(RecoveryEngine)
    assert "datetime.now()" not in src


def test_forecasting_uses_utc():
    src = _module_source(ForecastingEngine)
    assert "datetime.now()" not in src


def test_decay_uses_utc():
    src = _module_source(KnowledgeDecayEngine)
    assert "datetime.now()" not in src


def test_clipboard_actions_uses_utc():
    src = _module_source(ClipboardActionsEngine)
    assert "datetime.now()" not in src
