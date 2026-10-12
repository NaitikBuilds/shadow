
from shadow.hal.hybrid_backend import HybridBackend


class FakeBackend:
    def __init__(self, name: str, reply: str = "x", raises: bool = False):
        self.name = name
        self.reply = reply
        self.raises = raises
        self.calls = 0

    def generate_stream(self, prompt, **kwargs):
        self.calls += 1
        if self.raises:
            raise RuntimeError(f"{self.name} failed")
        yield self.reply

    def generate(self, prompt, **kwargs):
        return "".join(self.generate_stream(prompt, **kwargs))

    def embed(self, text):
        return [0.0] * 384

    @property
    def info(self):
        return {"backend": self.name}


class FakeHealth:
    def __init__(self, online: bool = True):
        self.online = online

    def is_online(self):
        return self.online


def test_online_routes_to_cloud():
    cloud = FakeBackend("cloud", "C")
    local = FakeBackend("local", "L")
    hybrid = HybridBackend(cloud, local, health=FakeHealth(online=True))
    assert hybrid.generate("hi") == "C"
    assert cloud.calls == 1
    assert local.calls == 0


def test_offline_routes_to_local():
    cloud = FakeBackend("cloud", "C")
    local = FakeBackend("local", "L")
    hybrid = HybridBackend(cloud, local, health=FakeHealth(online=False))
    assert hybrid.generate("hi") == "L"
    assert cloud.calls == 0
    assert local.calls == 1


def test_cloud_failure_falls_back_to_local():
    cloud = FakeBackend("cloud", raises=True)
    local = FakeBackend("local", "L")
    hybrid = HybridBackend(cloud, local, health=FakeHealth(online=True))
    assert hybrid.generate("hi") == "L"
    assert cloud.calls == 1
    assert local.calls == 1


def test_embed_uses_local():
    cloud = FakeBackend("cloud", "C")
    local = FakeBackend("local", "L")
    hybrid = HybridBackend(cloud, local, health=FakeHealth(online=True))
    emb = hybrid.embed("hi")
    assert len(emb) == 384
    assert cloud.calls == 0
    assert local.calls == 0  # embed doesn't count as generate


def test_info_reports_route():
    cloud = FakeBackend("cloud", "C")
    local = FakeBackend("local", "L")
    hybrid = HybridBackend(cloud, local, health=FakeHealth(online=True))
    hybrid.generate("hi")
    assert hybrid.info["route"] == "cloud"

    hybrid2 = HybridBackend(cloud, local, health=FakeHealth(online=False))
    hybrid2.generate("hi")
    assert hybrid2.info["route"] == "local_offline"


def test_close_is_safe():
    cloud = FakeBackend("cloud", "C")
    local = FakeBackend("local", "L")
    hybrid = HybridBackend(cloud, local, health=FakeHealth(online=True))
    hybrid.close()  # should not raise
