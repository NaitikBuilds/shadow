"""Tests for C09c: save_phase4_setting preserves YAML structure."""

from __future__ import annotations

from pathlib import Path

import yaml

from shadow.config import save_phase4_setting


def _write_cfg(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(text, encoding="utf-8")
    return p


MINIMAL = """\
# Header comment preserved
memory:
  db_path: shadow.db
  vector_dim: 384

phase4:
  # Ethical mirror section
  ethical_mirror_opt_out: false
  ethical_mirror_cloud_enabled: false
  auto_summary_enabled: false
"""


def test_flip_existing_key_true(tmp_path):
    p = _write_cfg(tmp_path, MINIMAL)
    save_phase4_setting("ethical_mirror_cloud_enabled", True, path=str(p))
    text = p.read_text(encoding="utf-8")
    assert "ethical_mirror_cloud_enabled: true" in text
    # Other keys unchanged
    assert "ethical_mirror_opt_out: false" in text
    assert "auto_summary_enabled: false" in text
    # Comments preserved
    assert "# Header comment preserved" in text
    assert "# Ethical mirror section" in text
    # Valid YAML
    data = yaml.safe_load(text)
    assert data["phase4"]["ethical_mirror_cloud_enabled"] is True
    assert data["phase4"]["auto_summary_enabled"] is False


def test_flip_back_to_false(tmp_path):
    p = _write_cfg(
        tmp_path,
        MINIMAL.replace(
            "ethical_mirror_cloud_enabled: false",
            "ethical_mirror_cloud_enabled: true",
        ),
    )
    save_phase4_setting("ethical_mirror_cloud_enabled", False, path=str(p))
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert data["phase4"]["ethical_mirror_cloud_enabled"] is False


def test_add_new_key_to_existing_section(tmp_path):
    cfg = MINIMAL.replace("  auto_summary_enabled: false\n", "")
    p = _write_cfg(tmp_path, cfg)
    save_phase4_setting("auto_summary_enabled", True, path=str(p))
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert data["phase4"]["auto_summary_enabled"] is True


def test_add_section_if_missing(tmp_path):
    p = _write_cfg(tmp_path, "memory:\n  db_path: x.db\n")
    save_phase4_setting("ethical_mirror_cloud_enabled", True, path=str(p))
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert data["phase4"]["ethical_mirror_cloud_enabled"] is True
    assert data["memory"]["db_path"] == "x.db"


def test_string_value_quoting(tmp_path):
    p = _write_cfg(tmp_path, MINIMAL)
    save_phase4_setting("bg_vision_model_preference", "florence2", path=str(p))
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert data["phase4"]["bg_vision_model_preference"] == "florence2"


def test_string_with_special_chars_quoted(tmp_path):
    p = _write_cfg(tmp_path, MINIMAL)
    save_phase4_setting("digest_schedule_time", "09:30", path=str(p))
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert data["phase4"]["digest_schedule_time"] == "09:30"
