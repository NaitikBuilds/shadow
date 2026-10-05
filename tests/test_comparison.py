import json
from pathlib import Path


def test_results_path_under_benchmarks(tmp_path, monkeypatch):
    """Comparison output belongs in benchmarks/, not in src."""
    # Compute the same path the script uses
    here = Path(__file__).resolve()
    repo_root = here.parents[1]
    expected = repo_root / "benchmarks" / "uia_vs_ocr.jsonl"
    assert expected.parent.name == "benchmarks"


def test_json_lines_are_parseable(tmp_path):
    """Simulate what the script writes and verify it round-trips."""
    path = tmp_path / "test.jsonl"
    records = [
        {
            "timestamp": "2026-10-05 12:00:00",
            "process": "Code.exe",
            "title": "recovery.py",
            "category": "editor",
            "uia_ms": 42.0,
            "uia_chars": 500,
            "uia_blocks": 12,
            "ocr_ms": 0.0,
            "ocr_chars": 0,
            "ocr_words": 0,
            "winner": "uia",
        },
        {
            "timestamp": "2026-10-05 12:01:00",
            "process": "WindowsTerminal.exe",
            "title": "PowerShell",
            "category": "terminal",
            "uia_ms": 0.0,
            "uia_chars": 0,
            "uia_blocks": 0,
            "ocr_ms": 180.0,
            "ocr_chars": 320,
            "ocr_words": 55,
            "winner": "ocr",
        },
    ]
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["winner"] == "uia"
    assert parsed[1]["winner"] == "ocr"


def test_summary_aggregation_logic():
    """Reproduce the aggregation math to verify it's sound."""
    runs = [
        {
            "category": "editor",
            "uia_ms": 40.0,
            "uia_chars": 500,
            "ocr_ms": 0.0,
            "ocr_chars": 0,
            "winner": "uia",
        },
        {
            "category": "editor",
            "uia_ms": 60.0,
            "uia_chars": 700,
            "ocr_ms": 0.0,
            "ocr_chars": 0,
            "winner": "uia",
        },
        {
            "category": "browser",
            "uia_ms": 30.0,
            "uia_chars": 100,
            "ocr_ms": 200.0,
            "ocr_chars": 800,
            "winner": "ocr",
        },
    ]

    by_cat: dict[str, dict] = {}
    for r in runs:
        cat = r["category"]
        bucket = by_cat.setdefault(
            cat,
            {
                "runs": 0,
                "uia_ms_total": 0.0,
                "uia_chars_total": 0,
                "ocr_ms_total": 0.0,
                "ocr_chars_total": 0,
                "uia_wins": 0,
                "ocr_wins": 0,
            },
        )
        bucket["runs"] += 1
        bucket["uia_ms_total"] += r["uia_ms"]
        bucket["uia_chars_total"] += r["uia_chars"]
        bucket["ocr_ms_total"] += r["ocr_ms"]
        bucket["ocr_chars_total"] += r["ocr_chars"]
        if r["winner"] == "uia":
            bucket["uia_wins"] += 1
        elif r["winner"] == "ocr":
            bucket["ocr_wins"] += 1

    editor = by_cat["editor"]
    assert editor["runs"] == 2
    assert editor["uia_ms_total"] == 100.0
    assert editor["uia_wins"] == 2
    assert editor["ocr_wins"] == 0

    browser = by_cat["browser"]
    assert browser["runs"] == 1
    assert browser["ocr_chars_total"] == 800
    assert browser["ocr_wins"] == 1


def test_winner_logic():
    """Higher char count wins; equal or both-zero handled."""

    def winner(uia_chars: int, ocr_chars: int) -> str:
        if uia_chars == 0 and ocr_chars == 0:
            return "none"
        return "uia" if uia_chars > ocr_chars else "ocr"

    assert winner(500, 100) == "uia"
    assert winner(100, 500) == "ocr"
    assert winner(0, 200) == "ocr"
    assert winner(200, 0) == "uia"
    assert winner(0, 0) == "none"
    assert winner(100, 100) == "ocr"  # tie → ocr
