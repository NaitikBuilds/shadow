

from shadow.hal.health import HealthMonitor


class FakeSocket:
    """Simulates socket.create_connection."""

    def __init__(self, succeed: bool = True):
        self.succeed = succeed

    def __call__(self, addr, timeout=None):
        if not self.succeed:
            raise OSError("connection refused")

        class _Ctx:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

        return _Ctx()


def test_first_check_returns_result(monkeypatch):
    monkeypatch.setattr("socket.create_connection", FakeSocket(succeed=True))
    monitor = HealthMonitor()
    assert monitor.is_online() is True


def test_offline_detected(monkeypatch):
    monkeypatch.setattr("socket.create_connection", FakeSocket(succeed=False))
    monitor = HealthMonitor()
    assert monitor.is_online() is False


def test_cache_avoids_reprobe(monkeypatch):
    calls = {"n": 0}

    def counter(addr, timeout=None):
        calls["n"] += 1
        raise OSError("nope")

    monkeypatch.setattr("socket.create_connection", counter)
    monitor = HealthMonitor(cache_sec=60)

    from shadow.hal.health import PROBE_HOSTS

    monitor.is_online()
    monitor.is_online()
    monitor.is_online()
    assert calls["n"] == len(PROBE_HOSTS)  # only first call probes


def test_force_check_ignores_cache(monkeypatch):
    calls = {"n": 0}

    def counter(addr, timeout=None):
        calls["n"] += 1
        raise OSError("nope")

    monkeypatch.setattr("socket.create_connection", counter)
    monitor = HealthMonitor(cache_sec=60)

    monitor.is_online()
    first_count = calls["n"]
    monitor.force_check()
    assert calls["n"] > first_count


def test_info_reports_state():
    monitor = HealthMonitor()
    info = monitor.info()
    assert "online" in info
    assert "cache_sec" in info
    assert info["cache_sec"] == 60
