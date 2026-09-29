from shadow.config import load_config


def test_load_config():
    cfg = load_config()
    assert "model" in cfg
    assert "memory" in cfg
    assert cfg["modes"]["default"] in {"lite", "balanced", "active"}
