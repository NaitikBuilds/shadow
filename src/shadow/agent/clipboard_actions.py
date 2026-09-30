"""Smart Clipboard Actions — suggest next steps based on copied content.

Reads recent clipboard observations and classifies each as one of:
URL, error, code, or plain text. Produces an Insight with a suggested
action hint. No action is executed — the panel shows the hint only.
"""

from datetime import datetime, timedelta

from .insight import Insight

# Markers that strongly indicate code rather than prose.
_CODE_MARKERS = (
    "def ",
    "class ",
    "import ",
    "from ",
    "return ",
    "const ",
    "let ",
    "var ",
    "async ",
    "await ",
    "=>",
    "};",
    ");",
)

# Markers that strongly indicate an error or stack trace.
_ERROR_MARKERS = (
    "Traceback (most recent call last)",
    "Stack trace",
    "Exception:",
    "Error:",
    '  File "',
    " at line ",
)


class ClipboardActionsEngine:
    """Suggests actions based on what was recently copied."""

    LOOKBACK_MIN = 30
    DEFAULT_LIMIT = 3
    MIN_TEXT_CHARS = 20

    # Score is multiplied by this per minute of age (fades out around 30 min).
    DECAY_PER_MIN = 0.03

    def __init__(self, memory):
        self.memory = memory

    def suggest(self, limit: int | None = None) -> list[Insight]:
        limit = limit or self.DEFAULT_LIMIT
        rows = self._recent_clipboard()
        insights: list[Insight] = []
        seen_kinds: set[str] = set()
        for row in rows:
            insight = self._classify_and_build(row)
            if insight is None:
                continue
            # Dedupe: only show one insight per content type per batch.
            if insight.kind in seen_kinds:
                continue
            seen_kinds.add(insight.kind)
            insights.append(insight)
            if len(insights) >= limit:
                break
        return insights

    # ---------- internals ----------

    def _recent_clipboard(self) -> list[tuple]:
        cutoff = (datetime.utcnow() - timedelta(minutes=self.LOOKBACK_MIN)).isoformat(
            sep=" ", timespec="seconds"
        )

        try:
            cur = self.memory.conn.cursor()
            cur.execute(
                "SELECT id, timestamp, content FROM observations "
                "WHERE source = 'clipboard' AND timestamp >= ? "
                "ORDER BY timestamp DESC LIMIT 10",
                (cutoff,),
            )
            return cur.fetchall()
        except Exception:
            return []

    def _classify_and_build(self, row: tuple) -> Insight | None:
        obs_id, ts, content = row
        text = self._strip_prefix(content)
        if len(text) < self.MIN_TEXT_CHARS:
            return None

        content_type = self._classify(text)
        insight = self._build_insight(content_type, text)

        # Apply age decay so older clipboard items score lower.
        try:
            from datetime import datetime

            age_min = (
                datetime.utcnow() - datetime.fromisoformat(ts)
            ).total_seconds() / 60.0
            decay = max(0.3, 1.0 - age_min * self.DECAY_PER_MIN)
            insight.score = round(insight.score * decay, 2)
        except (TypeError, ValueError):
            pass

        return insight

    @staticmethod
    def _strip_prefix(content: str) -> str:
        """Remove the 'Clipboard (N chars):\\n' prefix added by the observer."""
        text = (content or "").strip()
        if text.startswith("Clipboard ("):
            nl = text.find("\n")
            if nl >= 0:
                text = text[nl + 1 :]
        return text.strip()

    def _classify(self, text: str) -> str:
        if self._looks_like_url(text):
            return "url"
        if self._looks_like_error(text):
            return "error"
        if self._looks_like_code(text):
            return "code"
        return "text"

    @staticmethod
    def _looks_like_url(text: str) -> bool:
        stripped = text.strip()
        if "\n" in stripped:
            return False
        if len(stripped.split()) > 2:
            return False
        return stripped.startswith(("http://", "https://", "www."))

    @staticmethod
    def _looks_like_error(text: str) -> bool:
        return any(marker in text for marker in _ERROR_MARKERS)

    @staticmethod
    def _looks_like_code(text: str) -> bool:
        hits = sum(1 for marker in _CODE_MARKERS if marker in text)
        return hits >= 2

    @staticmethod
    def _build_insight(content_type: str, text: str) -> Insight:
        preview = text[:80].replace("\n", " ").strip()
        if content_type == "url":
            return Insight(
                kind="clipboard_url",
                title="Copied a link",
                body=f"Save to your reading list?  →  {preview}",
                score=0.6,
                action="Save to reading list",
                bypass_focus_shield=True,
            )
        if content_type == "error":
            return Insight(
                kind="clipboard_error",
                title="Copied an error",
                body=(
                    f"Want me to search your past for the same error?  →  " f"{preview}"
                ),
                score=0.75,
                action="Search past occurrences",
                bypass_focus_shield=True,
            )
        if content_type == "code":
            return Insight(
                kind="clipboard_code",
                title="Copied code",
                body=f"Save this snippet to project notes?  →  {preview}",
                score=0.6,
                action="Save snippet",
                bypass_focus_shield=True,
            )
        return Insight(
            kind="clipboard_text",
            title="Copied text",
            body=f"Save as a note?  →  {preview}",
            score=0.4,
            action="Save as note",
            bypass_focus_shield=True,
        )
