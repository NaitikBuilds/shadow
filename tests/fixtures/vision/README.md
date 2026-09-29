# Vision Test Fixtures

Golden images for the VLM accuracy suite (Phase 3.6).

## Required files (to be added in Phase 3.6)

| File | Content | Expected caption keywords |
|---|---|---|
| `error_dialog.png` | Windows error dialog | "error", "failed" |
| `bar_chart.png` | Simple bar chart | "chart", "bar", "values" |
| `line_chart.png` | Line graph | "chart", "trend", "increasing" |
| `code_block.png` | Python code snippet | "code", "function" |
| `math_equation.png` | Quadratic equation | "equation", "x", "=" |
| `photo_landscape.png` | Nature photo | "landscape", "sky", "trees" |
| `ui_settings.png` | Settings dialog | "settings", "options" |
| `pdf_figure.png` | Scientific figure | "figure", "diagram" |

Minimum 20 images total. Each image:
- 1024px on longest side (VLM input size)
- PNG format
- No PII (no names, emails, faces of real people)