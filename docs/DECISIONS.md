# SHADOW — Design Decisions Log

Every non-obvious technical choice, with the reasoning and any conditions
that would trigger a revisit. This is not a changelog — it's a rationale
record. Add an entry when a decision is non-reversible, expensive to
reverse, or likely to be questioned later.

Format: **date — decision** with *Reason* and *Revisit* lines.

---

## Language and runtime

**2026-09 — Use Python 3.11 (not 3.12, not 3.14).**
Reason: 3.14 lacks prebuilt wheels for `llama-cpp-python`, and 3.12+ has
partial wheel coverage for several dependencies. 3.11 has full support.
Revisit: When `llama-cpp-python` ships official 3.12+ Windows wheels.

**2026-09 — Use `llama-cpp-python` CPU wheel from oobabooga.**
Reason: Official PyPI wheels are not published for Windows. The community
CPU wheel is stable and widely used.
Revisit: When official Windows wheels ship.

**2026-09 — Do not use C# / WinUI 3 despite being Windows-first.**
Reason: Python's AI/ML ecosystem is significantly stronger; iteration speed
beats native polish for early development. Packaging in Phase 8 will handle
distribution concerns.
Revisit: If native performance becomes the bottleneck or if MSIX integration
requires a native host.

---

## Storage and persistence

**2026-09 — SQLite + `sqlite-vec` for vector memory.**
Reason: Fully local, zero-config, embeddable. Alternatives (Chroma, LanceDB,
FAISS) add process overhead or dependency weight without meaningful benefit
at SHADOW's scale.
Revisit: If observation count exceeds 10M or if ACID guarantees become a
bottleneck.

**2026-09 — Enable WAL mode on every connection.**
Reason: Crash-safe writes with concurrent readers. Standard SQLite best
practice for desktop apps.
Revisit: Never. This is the correct default.

**2026-09 — Versioned migration framework instead of ad-hoc schema edits.**
Reason: Every future phase adds tables. Without migrations, dev DBs become
unusable across commits.
Revisit: Never.

**2026-09 — `schema_meta` table for version, model hashes, and prune time.**
Reason: A single key-value table is simpler than a dedicated `settings`
table and handles the three meta fields we need.
Revisit: If meta entries grow beyond ~20 keys, consider typed columns.

---

## AI and models

**2026-09 — Qwen2.5-1.5B-Instruct Q4_K_M as the default chat model.**
Reason: Smallest model that produces coherent answers. Runs at ~10 tok/s on
i5-12450H with 6 threads.
Revisit: When a better 1.5B–3B model with equal CPU latency emerges.

**2026-09 — ONNX MiniLM-L6-v2 (quantized) for embeddings.**
Reason: 384-dim (matches sqlite-vec schema), ~90 MB, fast on CPU. Widely
used and well-tested.
Revisit: Only if retrieval quality becomes a bottleneck; consider bge-small
or gte-small.

**2026-09 — Rules-based entity extraction, not LLM-based.**
Reason: Fast, deterministic, no model load. Sufficient for project/topic/file
extraction.
Revisit: If entity quality becomes a bottleneck for retrieval or insights.

**2026-09 — Moondream2 planned for vision (Phase 3.6).**
Reason: 1.7 GB, 4–8 s per image on CPU. Smaller than Qwen2-VL-2B and
sufficient for chart/diagram/code recognition.
Revisit: After Phase 3.6 benchmarks; Qwen2-VL-2B or Florence-2 may win.

**2026-09 — No cloud API calls for core intelligence.**
Reason: Privacy is the product. Enforced by CI's network-isolation check.
Revisit: Post-v1.0 only, opt-in only, isolated-process only.

---

## Architecture

**2026-09 — Layered architecture with strict downward imports.**
Reason: Prevents circular dependencies and enables backend swaps (e.g.
Snapdragon NPU) without touching upper layers.
Revisit: Never.

**2026-09 — HAL interface (`InferenceBackend`) with lazy imports.**
Reason: The module must be importable on non-Windows systems for testing and
future ports. Backend-specific imports happen inside methods.
Revisit: Never.

**2026-09 — Three-thread model (main, observer, inference).**
Reason: Qt's UI thread must not block; the observer runs on its own cadence;
LLM generation runs once per query. Simpler than thread pools for this scale.
Revisit: If concurrent perception and generation cause contention.

**2026-09 — Minimize to tray, don't quit on window close.**
Reason: SHADOW is a background agent; closing the window shouldn't stop
observation. Full quit is a deliberate action.
Revisit: Never.

---

## Error handling

**2026-09 — Four-severity error taxonomy (Silent/Badge/Tray/Modal).**
Reason: Forces every failure mode to be classified. Users see only what they
can act on.
Revisit: If Modal errors become common enough to be annoying.

**2026-09 — Tracebacks to disk, never to the DB.**
Reason: Tracebacks contain file paths, variable names, and possibly user
content. Keeping them out of the DB preserves the "user owns their data"
promise.
Revisit: Never.

**2026-09 — Global `sys.excepthook` routes through ErrorReporter.**
Reason: Qt's default slot-exception handling silently swallows errors.
Overriding the hook ensures nothing is lost.
Revisit: Never.

---

## Perception sources

**2026-09 — Two-gate source system: config flag + consent.**
Reason: The config gate ships capabilities; the consent gate respects user
choice. Both must be true for a source to run.
Revisit: Never.

**2026-09 — Self-observation guard in observer (`_content_from`).**
Reason: SHADOW observing its own window creates feedback loops.
Revisit: If we ever build a "SHADOW as a screen-share demo" feature.

**2026-09 — Typing dynamics records timing only, never key content.**
Reason: Privacy. Explicit design invariant with an inline comment in
`typing.py`. The callback discards the key object immediately.
Revisit: Never.

**2026-09 — OCR garbage filter (`_looks_like_real_text`).**
Reason: Terminal output, symbol-heavy text, and case chaos produce useless
observations that pollute memory.
Revisit: If legitimate content is being filtered out.

**2026-09 — Documents seed their `seen` map on first tick.**
Reason: Prevents ingesting the entire Documents folder on launch.
Revisit: Never.

**2026-09 — Calendar WinRT source gracefully no-ops until MSIX.**
Reason: The `appointments` capability requires packaged distribution. Source
is present so it activates automatically after Phase 8.
Revisit: When packaging ships.

---

## Configuration

**2026-09 — YAML for config, not JSON or TOML.**
Reason: Human-readable, supports comments, familiar to non-developers.
Revisit: Never.

**2026-09 — Deep-merge partial config blocks with defaults.**
Reason: Users only specify overrides. Especially important for `perception.sources`,
where a partial override shouldn't reset every other source.
Revisit: Never.

---

## Testing and CI

**2026-09 — Pytest markers: slow / hardware / injection / network.**
Reason: Fast feedback loop in dev; full suite in CI. `--strict-markers`
prevents typos.
Revisit: Never.

**2026-09 — Network isolation enforced by static analysis.**
Reason: The privacy promise is verifiable, not just aspirational.
Revisit: If false positives become common.

**2026-09 — CI runs on Windows runner.**
Reason: SHADOW depends on `pywin32`, WinRT, and Windows APIs. Cross-platform
CI would pass for the wrong reasons.
Revisit: If we add a Linux port.

---

## Documentation

**2026-10-03 — Phase 3 (Proactive Intelligence) complete.**
Reason: 24 commits delivered the Insight framework, 8 proactive engines,
prompt-injection defense (PromptBuilder + taint), secret redaction, person
entity extraction, and insight feedback. Version tagged v0.3.0-proactive.
Revisit: Phase 3.5 (UIA structured screen) begins next.

**2026-10 — Proactive engines use UTC, not local time.**
Reason: Observations were already UTC (SQLite). Engines compared against
`datetime.now()` (local) causing every window filter to be off by the
local UTC offset. Fixed in Phase 3 Commit "fix(agent): use UTC consistently."
Revisit: Never.

**2026-10 — Redaction is applied before storage, not just before display.**
Reason: If only display were redacted, secrets would live in the DB and in
the vector embeddings. Redacting once, at write time, keeps both clean.
Revisit: Never.

**2026-10 — Person extraction requires exactly two capitalized tokens.**
Reason: Three-token phrases are usually product names (Visual Studio Code,
Visual Studio Code Insiders). Losing real three-word names is preferable to
false-positive noise. Users can add missed names to _PERSON_STOPWORDS.
Revisit: If real usage shows we're missing too many names.

**2026-10 — i18n deferred to Phase 8.**
Reason: Externalizing strings without actual translations is churn.
Phase 3 focuses on features. Localization lands when the UI is frozen.
Revisit: Phase 8.

**2026-09 — Separate PRD (private) from README (public).**
Reason: The README needs to be safe to hand to anyone; the PRD contains the
full vision.
Revisit: At public launch, decide what parts of the PRD become public.

**2026-09 — README uses understated positioning ("research project").**
Reason: Prevents casual visitors from copying the vision. The product
differentiation lives in the code and the PRD, not the README.
Revisit: When SHADOW has users and the positioning is a strength.

**2026-09 — BSL 1.1 license (not MIT, not AGPL).**
Reason: Allows reading, learning, and personal use; prevents commercial
forks; auto-converts to Apache 2.0 in four years.
Revisit: If the project becomes a business, replace with a commercial
license. If it becomes community-driven, consider switching to AGPL earlier.

---

## Adding a new decision

When making a non-trivial choice:

1. Add an entry under the relevant section.
2. Include the date (YYYY-MM).
3. State the decision, the reason, and the revisit condition.
4. Keep it under 5 lines.

If a decision is reversed, **don't delete the entry** — add a new one that
references the old one. The history matters.

