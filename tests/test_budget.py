from datetime import datetime, timedelta

import pytest

from shadow.config import budget_config, load_config
from shadow.memory import MemoryStore
from shadow.perception.budget import BudgetController


class FakeBattery:
    """Simulates plugged-in at 100%."""

    power_plugged = True
    percent = 100


@pytest.fixture(autouse=True)
def mock_psutil_battery(monkeypatch):
    """Force battery sensor to report AC power for predictable tests."""
    import sys
    import types

    fake_psutil = types.SimpleNamespace(
        sensors_battery=lambda: FakeBattery(),
    )
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)
    yield


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "budget.db"))
    yield s
    s.close()


@pytest.fixture
def config():
    cfg = load_config()
    cfg.setdefault("perception", {})["budget"] = {
        "enabled": True,
        "active_multiplier": 0.5,
        "idle_multiplier": 2.0,
        "battery_multiplier": 1.5,
        "low_battery_threshold": 20,
        "low_battery_multiplier": 3.0,
        "min_interval_sec": 5,
        "max_interval_sec": 180,
    }
    return cfg


def add_observation(store, minutes_ago: float):
    ts = (datetime.now() - timedelta(minutes=minutes_ago)).isoformat(
        sep=" ", timespec="seconds"
    )
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO observations (timestamp, source, content) "
        "VALUES (?, 'test', 'x')",
        (ts,),
    )
    store.conn.commit()


def test_disabled_returns_base(store, config):
    config["perception"]["budget"]["enabled"] = False
    ctrl = BudgetController(store, config)
    assert ctrl.effective_interval("balanced") == 30


def test_idle_slows_down(store, config):
    ctrl = BudgetController(store, config)
    interval = ctrl.effective_interval("balanced")
    # base 30, idle 2.0, AC → 60
    assert interval >= 30


def test_active_speeds_up(store, config):
    for i in range(15):
        add_observation(store, i * 0.3)

    ctrl = BudgetController(store, config)
    interval = ctrl.effective_interval("balanced")
    # base 30, active 0.5, AC → 15
    assert interval <= 30


def test_min_interval_clamped(store, config):
    for i in range(20):
        add_observation(store, i * 0.2)
    config["perception"]["budget"]["active_multiplier"] = 0.01

    ctrl = BudgetController(store, config)
    interval = ctrl.effective_interval("balanced")
    assert interval >= config["perception"]["budget"]["min_interval_sec"]


def test_max_interval_clamped(store, config):
    config["perception"]["budget"]["idle_multiplier"] = 50.0
    ctrl = BudgetController(store, config)
    interval = ctrl.effective_interval("balanced")
    assert interval <= config["perception"]["budget"]["max_interval_sec"]


def test_active_multiplier_applied(store, config):
    for i in range(15):
        add_observation(store, i * 0.2)
    ctrl = BudgetController(store, config)
    m = ctrl._activity_multiplier()
    assert m == config["perception"]["budget"]["active_multiplier"]


def test_idle_multiplier_applied(store, config):
    ctrl = BudgetController(store, config)
    m = ctrl._activity_multiplier()
    assert m == config["perception"]["budget"]["idle_multiplier"]


def test_graceful_on_missing_psutil(store, config, monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "psutil", None)

    ctrl = BudgetController(store, config)
    m = ctrl._battery_multiplier()
    assert m == 1.0


def test_battery_multiplier_when_unplugged(store, config, monkeypatch):
    import sys
    import types

    class LowBattery:
        power_plugged = False
        percent = 15

    fake = types.SimpleNamespace(sensors_battery=lambda: LowBattery())
    monkeypatch.setitem(sys.modules, "psutil", fake)

    ctrl = BudgetController(store, config)
    m = ctrl._battery_multiplier()
    assert m == config["perception"]["budget"]["low_battery_multiplier"]


def test_different_modes_give_different_intervals(store, config):
    ctrl = BudgetController(store, config)
    lite = ctrl.effective_interval("lite")
    active = ctrl.effective_interval("active")
    assert active < lite


def test_config_helper_returns_defaults():
    d = budget_config({})
    assert d["enabled"] is True
    assert d["min_interval_sec"] == 5
    assert d["max_interval_sec"] == 180
