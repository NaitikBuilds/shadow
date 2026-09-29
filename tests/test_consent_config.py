from shadow.config import consent_channels, is_consented, load_config


def test_consent_channels_present():
    cfg = load_config()
    channels = consent_channels(cfg)
    assert "screen_capture" in channels
    assert "typing_dynamics" in channels
    assert len(channels) >= 6


def test_consent_defaults_off():
    cfg = load_config()
    for ch in consent_channels(cfg):
        assert is_consented(cfg, ch) is False


def test_observation_block_present():
    cfg = load_config()
    assert "observation" in cfg
    assert cfg["observation"]["indicator_enabled"] is True
