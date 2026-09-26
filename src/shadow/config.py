from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_config(path: str = "config.yaml") -> dict:
    config_path = ROOT / path
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def consent_channels(config: dict) -> list[str]:
    """Return the list of consent channel names defined in config."""
    return list(config.get("consent", {}).keys())


def is_consented(config: dict, channel: str) -> bool:
    """Check whether a specific channel is consented in config."""
    return bool(config.get("consent", {}).get(channel, False))