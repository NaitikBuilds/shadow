import sys

import pytest

from shadow.perception import MonitorInfo
from shadow.perception.monitors import (
    active_monitor,
    list_monitors,
    monitor_for_rect,
    primary_monitor,
)


def test_monitor_info_bounds():
    m = MonitorInfo(
        index=0,
        left=0,
        top=0,
        right=1920,
        bottom=1080,
        work_left=0,
        work_top=0,
        work_right=1920,
        work_bottom=1040,
        is_primary=True,
    )
    assert m.bounds == (0, 0, 1920, 1080)
    assert m.work_area == (0, 0, 1920, 1040)
    assert m.width == 1920
    assert m.height == 1080


def test_monitor_info_contains():
    m = MonitorInfo(
        index=0,
        left=0,
        top=0,
        right=1920,
        bottom=1080,
        work_left=0,
        work_top=0,
        work_right=1920,
        work_bottom=1040,
        is_primary=True,
    )
    assert m.contains(100, 100) is True
    assert m.contains(0, 0) is True
    assert m.contains(1920, 1080) is False  # right/bottom exclusive
    assert m.contains(-1, 100) is False
    assert m.contains(100, -1) is False


def test_monitor_info_second_monitor():
    m = MonitorInfo(
        index=1,
        left=1920,
        top=0,
        right=3840,
        bottom=1080,
        work_left=1920,
        work_top=0,
        work_right=3840,
        work_bottom=1040,
        is_primary=False,
    )
    assert m.contains(2000, 500) is True
    assert m.contains(100, 500) is False


def test_monitor_info_to_dict():
    m = MonitorInfo(
        index=0,
        left=0,
        top=0,
        right=1920,
        bottom=1080,
        work_left=0,
        work_top=0,
        work_right=1920,
        work_bottom=1040,
        is_primary=True,
        dpi_scale=1.25,
    )
    d = m.to_dict()
    assert d["index"] == 0
    assert d["bounds"] == [0, 0, 1920, 1080]
    assert d["is_primary"] is True
    assert d["dpi_scale"] == 1.25


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_list_monitors_returns_at_least_one():
    monitors = list_monitors()
    assert len(monitors) >= 1
    for m in monitors:
        assert m.width > 0
        assert m.height > 0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_primary_monitor_exists():
    m = primary_monitor()
    assert m is not None
    assert m.is_primary is True


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_monitor_for_rect_returns_something():
    m = monitor_for_rect((100, 100, 500, 400))
    assert m is not None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_active_monitor_returns_or_none():
    # May return None if no foreground window, that's fine
    m = active_monitor()
    if m is not None:
        assert m.width > 0
        assert m.height > 0
