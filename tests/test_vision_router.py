
import pytest

from shadow.hal.vision_router import (
    VisionRouter,
    VisionRoutingError,
)


class FakeLocalVision:
    def __init__(self, result="local description"):
        self.result = result
        self.calls = 0

    def analyze(self, image_bytes, task="caption", prompt=""):
        self.calls += 1
        return self.result


class FakeCloudPool:
    def __init__(self, result="cloud description", error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def understand_image(self, image_bytes, task="caption", prompt=""):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


class FakeConsent:
    def __init__(self, enabled=True):
        self.enabled = enabled

    def get_consent(self, channel):
        assert channel == "vision_cloud"
        return self.enabled


class FakeHealth:
    def __init__(self, online=True):
        self.online = online

    def is_online(self):
        return self.online


def make_router(
    *,
    cloud_enabled=True,
    consent=True,
    online=True,
    require_preview=True,
    authorized=True,
    cloud_result="cloud description",
    cloud_error=None,
    local_result="local description",
    fallback=True,
):
    local = FakeLocalVision(local_result)
    cloud = FakeCloudPool(cloud_result, cloud_error)

    router = VisionRouter(
        local_service=local,
        cloud_pool=cloud,
        config={
            "cloud": {
                "enabled": cloud_enabled,
                "require_preview": require_preview,
                "fallback_to_local": fallback,
            }
        },
        health=FakeHealth(online),
        consent_store=FakeConsent(consent),
    )

    return router, local, cloud, authorized


def test_cloud_used_when_authorized():
    router, local, cloud, authorized = make_router()

    result = router.analyze(
        b"valid image bytes",
        authorized=authorized,
    )

    assert result == "cloud description"
    assert cloud.calls == 1
    assert local.calls == 0
    assert router.last_result.route == "cloud"


@pytest.mark.parametrize(
    "overrides",
    [
        {"cloud_enabled": False},
        {"consent": False},
        {"online": False},
        {"authorized": False},
    ],
)
def test_ineligible_cloud_request_uses_local(overrides):
    router, local, cloud, authorized = make_router(**overrides)

    result = router.analyze(
        b"valid image bytes",
        authorized=authorized,
    )

    assert result == "local description"
    assert local.calls == 1
    assert cloud.calls == 0
    assert router.last_result.route == "local"


def test_sensitive_window_never_reaches_cloud():
    router, local, cloud, authorized = make_router()

    result = router.analyze(
        b"valid image bytes",
        authorized=authorized,
        window_metadata={"is_sensitive": True},
    )

    assert result == "local description"
    assert cloud.calls == 0
    assert local.calls == 1


def test_cloud_failure_uses_local_fallback():
    router, local, cloud, authorized = make_router(
        cloud_error=RuntimeError("simulated provider failure"),
    )

    result = router.analyze(
        b"valid image bytes",
        authorized=authorized,
    )

    assert result == "local description"
    assert cloud.calls == 1
    assert local.calls == 1
    assert router.last_result.route == "local"


def test_cloud_failure_without_fallback_raises():
    router, _, _, authorized = make_router(
        cloud_error=RuntimeError("simulated provider failure"),
        fallback=False,
    )

    with pytest.raises(VisionRoutingError):
        router.analyze(
            b"valid image bytes",
            authorized=authorized,
        )


def test_empty_image_is_rejected():
    router, _, cloud, authorized = make_router()

    with pytest.raises(VisionRoutingError):
        router.analyze(b"", authorized=authorized)

    assert cloud.calls == 0


def test_local_only_never_calls_cloud():
    router, local, cloud, authorized = make_router()

    result = router.analyze(
        b"valid image bytes",
        authorized=authorized,
        local_only=True,
    )

    assert result == "local description"
    assert local.calls == 1
    assert cloud.calls == 0
