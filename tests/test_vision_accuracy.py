"""Local VLM accuracy benchmark for SHADOW Phase 3.6, Commit 14.

The benchmark generates 20 deterministic synthetic images, runs them
through the existing local VisionService, and records caption quality
signals and inference latency.

Model-dependent tests are opt-in:

    $env:SHADOW_RUN_VISION_ACCURACY = "1"
    pytest tests/test_vision_accuracy.py -v -s

No cloud provider is used.
"""

from __future__ import annotations

import io
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont


@dataclass(frozen=True)
class AccuracyCase:
    """One reproducible visual benchmark case."""

    case_id: str
    title: str
    scene: str
    visible_text: tuple[str, ...]
    expected_concepts: tuple[str, ...]


CASES = (
    AccuracyCase(
        "01",
        "Basic shapes",
        "shapes",
        ("RED CIRCLE", "BLUE SQUARE", "GREEN TRIANGLE"),
        ("circle", "square", "triangle"),
    ),
    AccuracyCase(
        "02",
        "Monthly sales chart",
        "bar_chart",
        ("SALES BY MONTH", "JAN", "FEB", "MAR"),
        ("bar chart", "sales", "month"),
    ),
    AccuracyCase(
        "03",
        "Temperature line chart",
        "line_chart",
        ("WEEKLY TEMPERATURE", "MON", "TUE", "WED", "THU"),
        ("line chart", "temperature", "week"),
    ),
    AccuracyCase(
        "04",
        "Expense pie chart",
        "pie_chart",
        ("MONTHLY EXPENSES", "RENT", "FOOD", "TRAVEL"),
        ("pie chart", "expenses", "rent"),
    ),
    AccuracyCase(
        "05",
        "Terminal error",
        "terminal",
        (
            "ModuleNotFoundError",
            "No module named 'requests'",
        ),
        ("terminal", "ModuleNotFoundError", "requests"),
    ),
    AccuracyCase(
        "06",
        "Python code editor",
        "code",
        (
            "def calculate_total(items):",
            "    return sum(items)",
        ),
        ("python", "function", "return"),
    ),
    AccuracyCase(
        "07",
        "Browser article",
        "article",
        (
            "CLIMATE CHANGE",
            "Renewable energy",
            "Solar and wind power",
        ),
        ("article", "climate change", "renewable energy"),
    ),
    AccuracyCase(
        "08",
        "Task checklist",
        "checklist",
        (
            "PROJECT TASKS",
            "[x] Write tests",
            "[x] Fix bugs",
            "[ ] Deploy application",
        ),
        ("checklist", "tasks", "tests"),
    ),
    AccuracyCase(
        "09",
        "Calendar",
        "calendar",
        ("WEEKLY CALENDAR", "MON", "TUE", "WED", "THU", "FRI"),
        ("calendar", "week", "meeting"),
    ),
    AccuracyCase(
        "10",
        "Email interface",
        "email",
        (
            "PROJECT UPDATE",
            "Subject: API release",
            "Deadline: Friday",
        ),
        ("email", "project", "deadline"),
    ),
    AccuracyCase(
        "11",
        "Flowchart",
        "flowchart",
        ("START", "PROCESS", "END"),
        ("flowchart", "start", "process", "end"),
    ),
    AccuracyCase(
        "12",
        "Warning dialog",
        "warning",
        ("WARNING", "Battery level is low"),
        ("warning", "battery", "low"),
    ),
    AccuracyCase(
        "13",
        "Progress indicator",
        "progress",
        ("DOWNLOAD PROGRESS", "75%"),
        ("progress", "75%"),
    ),
    AccuracyCase(
        "14",
        "Data table",
        "table",
        ("STUDENT", "SCORE", "Asha", "92", "Rahul", "85"),
        ("table", "student", "score"),
    ),
    AccuracyCase(
        "15",
        "File explorer",
        "files",
        ("PROJECT FILES", "report.pdf", "project.py", "README.md"),
        ("files", "report.pdf", "project.py"),
    ),
    AccuracyCase(
        "16",
        "Login form",
        "login",
        ("SIGN IN", "Username", "Password", "Log in"),
        ("login", "username", "password"),
    ),
    AccuracyCase(
        "17",
        "Solar energy diagram",
        "solar",
        ("SOLAR ENERGY", "SUN", "SOLAR PANEL", "BATTERY"),
        ("solar", "sun", "panel", "battery"),
    ),
    AccuracyCase(
        "18",
        "Map and route",
        "map",
        ("ROUTE TO DESTINATION", "START", "DESTINATION"),
        ("map", "route", "destination"),
    ),
    AccuracyCase(
        "19",
        "Before and after comparison",
        "comparison",
        ("BEFORE", "AFTER", "IMPROVEMENT"),
        ("before", "after", "comparison"),
    ),
    AccuracyCase(
        "20",
        "Invoice",
        "invoice",
        ("INVOICE", "Subtotal: $200.00", "Total: $245.00"),
        ("invoice", "subtotal", "total"),
    ),
)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a scalable font with cross-platform fallbacks."""
    for name in (
        "DejaVuSans.ttf",
        "arial.ttf",
        "LiberationSans-Regular.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue

    return ImageFont.load_default()


def _draw_wrapped_lines(
    draw: ImageDraw.ImageDraw,
    lines: tuple[str, ...],
    x: int,
    y: int,
    spacing: int = 38,
) -> None:
    """Draw text lines with enough spacing for visual recognition."""
    font = _font(22)

    for line in lines:
        draw.text((x, y), line, fill="black", font=font)
        y += spacing


def render_case(case: AccuracyCase) -> bytes:
    """Generate a deterministic PNG for a benchmark case."""
    image = Image.new("RGB", (800, 500), "white")
    draw = ImageDraw.Draw(image)

    draw.rectangle((10, 10, 790, 490), outline="#777777", width=2)
    draw.text(
        (30, 25),
        case.title,
        fill="black",
        font=_font(30),
    )

    draw.line((25, 80, 775, 80), fill="#aaaaaa", width=2)

    if case.scene == "shapes":
        draw.ellipse((80, 150, 200, 270), fill="red")
        draw.rectangle((300, 150, 420, 270), fill="blue")
        draw.polygon(
            [(550, 270), (610, 150), (670, 270)],
            fill="green",
        )
        _draw_wrapped_lines(
            draw,
            case.visible_text,
            60,
            320,
        )

    elif case.scene == "bar_chart":
        draw.line((100, 380, 700, 380), fill="black", width=3)
        draw.line((100, 130, 100, 380), fill="black", width=3)

        for x, height, label in (
            (180, 120, "JAN"),
            (330, 180, "FEB"),
            (480, 230, "MAR"),
        ):
            draw.rectangle(
                (x, 380 - height, x + 80, 380),
                fill="#3977c3",
            )
            draw.text(
                (x + 10, 395),
                label,
                fill="black",
                font=_font(20),
            )

    elif case.scene == "line_chart":
        draw.line((100, 390, 700, 390), fill="black", width=3)
        draw.line((100, 130, 100, 390), fill="black", width=3)

        points = [
            (140, 330),
            (260, 300),
            (380, 260),
            (500, 220),
            (640, 150),
        ]
        draw.line(points, fill="#2478c8", width=5)

        for x, y in points:
            draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill="red")

    elif case.scene == "pie_chart":
        draw.pieslice(
            (230, 130, 520, 420),
            start=0,
            end=180,
            fill="#3977c3",
            outline="white",
        )
        draw.pieslice(
            (230, 130, 520, 420),
            start=180,
            end=270,
            fill="#f0a43c",
            outline="white",
        )
        draw.pieslice(
            (230, 130, 520, 420),
            start=270,
            end=360,
            fill="#52a76b",
            outline="white",
        )
        _draw_wrapped_lines(draw, case.visible_text, 550, 170)

    elif case.scene == "terminal":
        draw.rectangle((30, 110, 770, 455), fill="#202020")
        _draw_wrapped_lines(
            draw,
            case.visible_text,
            55,
            170,
            spacing=65,
        )

        # Redraw the terminal text in a contrasting color.
        for i, line in enumerate(case.visible_text):
            draw.text(
                (55, 170 + i * 65),
                line,
                fill="#e8e8e8",
                font=_font(22),
            )

    elif case.scene == "code":
        draw.rectangle((30, 110, 770, 455), fill="#f1f1f1")
        _draw_wrapped_lines(
            draw,
            case.visible_text,
            65,
            180,
            spacing=65,
        )

    elif case.scene == "article":
        _draw_wrapped_lines(
            draw,
            case.visible_text,
            50,
            130,
            spacing=65,
        )

        for y in (340, 375, 410):
            draw.line((50, y, 730, y), fill="#cccccc", width=3)

    elif case.scene == "checklist":
        y = 145
        for line in case.visible_text[1:]:
            draw.rectangle((65, y, 92, y + 27), outline="black", width=2)

            if line.startswith("[x]"):
                draw.line(
                    (70, y + 12, 78, y + 20, 90, y + 5),
                    fill="green",
                    width=3,
                )

            draw.text(
                (115, y),
                line[4:],
                fill="black",
                font=_font(22),
            )
            y += 65

    elif case.scene == "calendar":
        x0, y0 = 50, 130
        cell_w, cell_h = 110, 65

        for row in range(4):
            for col in range(6):
                x = x0 + col * cell_w
                y = y0 + row * cell_h
                draw.rectangle(
                    (x, y, x + cell_w, y + cell_h),
                    outline="#888888",
                )

                if row == 0:
                    label = ("MON", "TUE", "WED", "THU", "FRI", "SAT")[col]
                else:
                    label = str((row - 1) * 6 + col + 1)

                draw.text(
                    (x + 8, y + 8),
                    label,
                    fill="black",
                    font=_font(16),
                )

        draw.rectangle((275, 195, 375, 245), fill="#f6d365")

    elif case.scene == "email":
        draw.rectangle((40, 120, 760, 440), outline="#888888", width=2)
        _draw_wrapped_lines(draw, case.visible_text[1:], 70, 170, spacing=80)

    elif case.scene == "flowchart":
        boxes = [
            (80, 200, 220, 270),
            (330, 200, 470, 270),
            (580, 200, 720, 270),
        ]

        for box, label in zip(boxes, case.visible_text):
            draw.rectangle(box, outline="#3977c3", width=3)
            draw.text(
                (box[0] + 20, box[1] + 20),
                label,
                fill="black",
                font=_font(20),
            )

        draw.line((220, 235, 330, 235), fill="black", width=3)
        draw.line((470, 235, 580, 235), fill="black", width=3)

    elif case.scene == "warning":
        draw.polygon(
            [(400, 120), (550, 370), (250, 370)],
            fill="#ffcc33",
            outline="black",
        )
        draw.text(
            (385, 210),
            "!",
            fill="black",
            font=_font(80),
        )
        _draw_wrapped_lines(draw, case.visible_text, 65, 400)

    elif case.scene == "progress":
        draw.rectangle((80, 220, 720, 290), outline="black", width=3)
        draw.rectangle((83, 223, 560, 287), fill="#4ca66b")
        draw.text(
            (330, 320),
            "75%",
            fill="black",
            font=_font(35),
        )

    elif case.scene == "table":
        rows = [
            ("STUDENT", "SCORE"),
            ("Asha", "92"),
            ("Rahul", "85"),
        ]
        x0, y0 = 150, 140

        for row_index, row in enumerate(rows):
            for col_index, value in enumerate(row):
                x = x0 + col_index * 250
                y = y0 + row_index * 80

                draw.rectangle(
                    (x, y, x + 250, y + 80),
                    outline="#777777",
                    width=2,
                )
                draw.text(
                    (x + 20, y + 20),
                    value,
                    fill="black",
                    font=_font(24),
                )

    elif case.scene == "files":
        draw.rectangle((35, 110, 765, 455), outline="#888888", width=2)
        _draw_wrapped_lines(draw, case.visible_text, 75, 145, spacing=75)

    elif case.scene == "login":
        draw.rectangle((180, 115, 620, 450), outline="#888888", width=2)
        draw.text((235, 150), "SIGN IN", fill="black", font=_font(30))
        draw.text((235, 225), "Username", fill="black", font=_font(20))
        draw.rectangle((235, 255, 565, 295), outline="#777777")
        draw.text((235, 320), "Password", fill="black", font=_font(20))
        draw.rectangle((235, 350, 565, 390), outline="#777777")
        draw.rectangle((235, 405, 350, 440), fill="#3977c3")

    elif case.scene == "solar":
        draw.ellipse((75, 150, 175, 250), fill="#f4c542")

        draw.rectangle((300, 190, 440, 280), fill="#3977c3")
        for x in (335, 370, 405):
            draw.line((x, 190, x, 280), fill="white", width=2)

        draw.rectangle((575, 190, 700, 290), outline="#555555", width=3)
        draw.line((440, 235, 575, 235), fill="black", width=3)
        _draw_wrapped_lines(
            draw,
            ("SUN", "SOLAR PANEL", "BATTERY"),
            55,
            330,
            spacing=45,
        )

    elif case.scene == "map":
        for x in range(70, 750, 80):
            draw.line((x, 120, x, 440), fill="#dddddd", width=2)

        for y in range(130, 450, 60):
            draw.line((55, y, 750, y), fill="#dddddd", width=2)

        route = [(100, 380), (230, 320), (330, 340), (460, 230), (650, 160)]
        draw.line(route, fill="#3478db", width=6)

        for x, y in (route[0], route[-1]):
            draw.ellipse((x - 10, y - 10, x + 10, y + 10), fill="red")

    elif case.scene == "comparison":
        draw.rectangle((40, 120, 380, 430), outline="#888888", width=2)
        draw.rectangle((420, 120, 760, 430), outline="#888888", width=2)

        draw.text((80, 155), "BEFORE", fill="black", font=_font(25))
        draw.text((460, 155), "AFTER", fill="black", font=_font(25))

        for y in (220, 260, 300, 340):
            draw.line((80, y, 320, y), fill="#c66b6b", width=5)
            draw.line((460, y, 700, y), fill="#55a66a", width=5)

    elif case.scene == "invoice":
        draw.rectangle((60, 115, 740, 450), outline="#888888", width=2)
        _draw_wrapped_lines(draw, case.visible_text, 95, 160, spacing=80)

    return _to_png_bytes(image)


def _to_png_bytes(image: Image.Image) -> bytes:
    """Encode a generated image in memory without creating source files."""
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _normalize(text: str) -> str:
    """Normalize caption text for approximate concept matching."""
    return re.sub(r"\s+", " ", text.lower()).strip()


def test_accuracy_suite_contains_twenty_cases():
    assert len(CASES) == 20
    assert len({case.case_id for case in CASES}) == 20


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_accuracy_fixture_is_a_valid_png(case):
    """Check that every generated fixture can be decoded as an image."""
    payload = render_case(case)

    with Image.open(io.BytesIO(payload)) as image:
        assert image.format == "PNG"
        assert image.width == 800
        assert image.height == 500


@pytest.mark.hardware
@pytest.mark.slow
def test_local_vlm_accuracy_benchmark(tmp_path, capsys):
    """Run the actual local model and generate a reviewable report.

    This test is opt-in because it requires the local vision model.
    It intentionally does not invent an accuracy threshold: the PRD
    specifies 20 images but does not define a numerical score cutoff.
    """
    if os.environ.get("SHADOW_RUN_VISION_ACCURACY") != "1":
        pytest.skip("Set SHADOW_RUN_VISION_ACCURACY=1 to run the local VLM benchmark.")

    from shadow.config import load_config, vision_config
    from shadow.hal import Moondream2Backend, VisionService

    config = load_config()
    vcfg = vision_config(config)

    text_path = Path(vcfg["text_model_path"])
    mmproj_path = Path(vcfg["mmproj_path"])

    if not text_path.is_file() or not mmproj_path.is_file():
        pytest.skip(
            "Local vision model files are missing; install the configured "
            "model before running the accuracy benchmark."
        )

    service = VisionService(
        lambda: Moondream2Backend(
            text_model_path=str(text_path),
            mmproj_path=str(mmproj_path),
            n_threads=vcfg.get("n_threads") or None,
        )
    )

    results = []

    try:
        for case in CASES:
            payload = render_case(case)

            started = time.perf_counter()
            caption = service.caption(payload)
            elapsed = time.perf_counter() - started

            caption_text = str(caption or "").strip()
            normalized_caption = _normalize(caption_text)

            matched = [
                term
                for term in case.expected_concepts
                if term.lower() in normalized_caption
            ]

            results.append(
                {
                    "case_id": case.case_id,
                    "title": case.title,
                    "expected_concepts": list(case.expected_concepts),
                    "matched_concepts": matched,
                    "concept_match_ratio": round(
                        len(matched) / len(case.expected_concepts), 3
                    ),
                    "caption": caption_text,
                    "latency_seconds": round(elapsed, 3),
                    "non_empty_caption": bool(caption_text),
                }
            )
    finally:
        service.close()

    non_empty = sum(item["non_empty_caption"] for item in results)
    matched_cases = sum(bool(item["matched_concepts"]) for item in results)

    report = {
        "benchmark": "SHADOW Phase 3.6 Commit 14",
        "backend": "local Moondream2",
        "case_count": len(results),
        "non_empty_captions": non_empty,
        "cases_with_concept_matches": matched_cases,
        "concept_match_rate": round(matched_cases / len(results), 3),
        "average_latency_seconds": round(
            sum(item["latency_seconds"] for item in results) / len(results),
            3,
        ),
        "results": results,
    }

    report_path = tmp_path / "vision_accuracy_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nAccuracy report: {report_path}")

    # The test must not silently accept an empty or broken model output.
    assert len(results) == 20
    assert non_empty == 20, (
        f"Expected 20 non-empty captions, received {non_empty}. "
        f"See report: {report_path}"
    )
