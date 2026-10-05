"""Stuck Detector — detect when the user is stuck across the workflow.

Extends Silent Pair Partner beyond code. Three patterns:

  1. Static window — same title for N+ minutes while actively working
  2. Alternation  — rapid back-and-forth between exactly two windows
  3. Error visible — error markers in recent observations

Unlike perception-level detectors, this uses only signals that work
everywhere: window titles, timestamps, and content markers. No UIA
dependency, so it works for Chromium apps, terminals, editors, and
native apps alike.
"""

from datetime import datetime, timedelta

from .insight import Insight

_ERROR_MARKERS = (
    "Traceback (most recent call last)",
    "Stack trace",
    "TypeError:",
    "ValueError:",
    "RuntimeError:",
    "KeyError:",
    "AttributeError:",
    "ImportError:",
    "IndexError:",
    "SyntaxError:",
    'File "',
    "Exception:",
    "Error:",
    "error:",
)


class StuckDetector:
    """Detects when the user appears to be stuck."""

    DEFAULT_STATIC_MINUTES = 20
    DEFAULT_ALTERNATION_MINUTES = 15
    DEFAULT_ALTERNATION_COUNT = 8
    DEFAULT_ERROR_LOOKBACK = 5

    RECENT_ACTIVITY_MINUTES = 5

    def __init__(self, memory, config=None):
        self.memory = memory
        cfg = ((config or {}).get("agent") or {}).get("stuck") or {}
        self.enabled = bool(cfg.get("enabled", True))
        self.static_minutes = int(
            cfg.get("static_minutes", self.DEFAULT_STATIC_MINUTES)
        )
        self.alternation_minutes = int(
            cfg.get("alternation_minutes", self.DEFAULT_ALTERNATION_MINUTES)
        )
        self.alternation_count = int(
            cfg.get("alternation_count", self.DEFAULT_ALTERNATION_COUNT)
        )
        self.error_lookback = int(
            cfg.get("error_lookback_minutes", self.DEFAULT_ERROR_LOOKBACK)
        )

    # ---------- public API ----------

    def find_stuck(self, limit: int = 3) -> list[Insight]:
        if not self.enabled:
            return []

        insights: list[Insight] = []
        insights.extend(self._detect_static())
        insights.extend(self._detect_alternation())
        insights.extend(self._detect_errors())

        best: dict[str, Insight] = {}
        for i in insights:
            existing = best.get(i.title)
            if existing is None or i.score > existing.score:
                best[i.title] = i

        ordered = sorted(best.values(), key=lambda i: i.score, reverse=True)
        return ordered[:limit]

    # ---------- signal 1: static ----------

    def _detect_static(self) -> list[Insight]:
        cutoff = (
            datetime.utcnow() - timedelta(minutes=self.static_minutes + 10)
        ).isoformat(sep=" ", timespec="seconds")

        parsed = self._load_title_events(cutoff)
        if len(parsed) < 3:
            return []

        # Require recent activity: user was actually working recently
        last_at = parsed[-1][0]
        if (
            datetime.utcnow() - last_at
        ).total_seconds() / 60.0 > self.RECENT_ACTIVITY_MINUTES:
            return []

        # All observations must share the same title
        titles = {t for _, t in parsed}
        if len(titles) != 1:
            return []

        first_at = parsed[0][0]
        span_min = (last_at - first_at).total_seconds() / 60.0
        if span_min < self.static_minutes:
            return []

        title = parsed[-1][1]
        score = round(min(0.75, 0.3 + span_min / 120.0), 2)

        return [
            Insight(
                kind="stuck_static",
                title=f"Still on: {title[:60]}",
                body=(
                    f"You've been on the same window for about "
                    f"{int(span_min)} minutes. Take a break or switch?"
                ),
                score=score,
                action="Stretch / switch",
                bypass_focus_shield=True,
            )
        ]

    # ---------- signal 2: alternation ----------

    def _detect_alternation(self) -> list[Insight]:
        cutoff = (
            datetime.utcnow() - timedelta(minutes=self.alternation_minutes)
        ).isoformat(sep=" ", timespec="seconds")

        parsed = self._load_title_events(cutoff)
        if len(parsed) < self.alternation_count:
            return []

        titles = [t for _, t in parsed]
        unique = set(titles)
        if len(unique) != 2:
            return []

        transitions = sum(
            1 for i in range(1, len(titles)) if titles[i] != titles[i - 1]
        )
        if transitions < self.alternation_count:
            return []

        a, b = sorted(unique)
        score = round(
            min(0.7, 0.4 + (transitions - self.alternation_count) * 0.03),
            2,
        )

        return [
            Insight(
                kind="stuck_alternation",
                title="Back-and-forth between two windows",
                body=(
                    f'You switched between "{a[:40]}" and "{b[:40]}" '
                    f"{transitions} times in {self.alternation_minutes} "
                    f"minutes. Stuck on something?"
                ),
                score=score,
                action="Ask SHADOW for help",
                bypass_focus_shield=True,
            )
        ]

    # ---------- signal 3: errors ----------

    def _detect_errors(self) -> list[Insight]:
        cutoff = (datetime.utcnow() - timedelta(minutes=self.error_lookback)).isoformat(
            sep=" ", timespec="seconds"
        )

        try:
            cur = self.memory.conn.cursor()
            cur.execute(
                "SELECT source, content FROM observations "
                "WHERE timestamp >= ? ORDER BY id DESC LIMIT 50",
                (cutoff,),
            )
            rows = cur.fetchall()
        except Exception:
            return []

        seen: set[str] = set()
        insights: list[Insight] = []

        for _source, content in rows:
            text = content or ""
            marker = self._find_error_marker(text)
            if not marker:
                continue

            key = marker.lower()
            if key in seen:
                continue
            seen.add(key)

            preview = self._extract_error_preview(text, marker)
            insights.append(
                Insight(
                    kind="stuck_error",
                    title=f"Error visible: {marker}",
                    body=(
                        f"Want me to search your past for this error?  →  " f"{preview}"
                    ),
                    score=0.7,
                    action="Search past occurrences",
                    bypass_focus_shield=True,
                )
            )

            if len(insights) >= 2:
                break

        return insights

    # ---------- helpers ----------

    def _load_title_events(self, cutoff: str) -> list[tuple[datetime, str]]:
        try:
            cur = self.memory.conn.cursor()
            cur.execute(
                "SELECT timestamp, content FROM observations "
                "WHERE source = 'active_window' AND timestamp >= ? "
                "ORDER BY timestamp ASC",
                (cutoff,),
            )
            rows = cur.fetchall()
        except Exception:
            return []

        parsed: list[tuple[datetime, str]] = []
        for ts, content in rows:
            try:
                t = datetime.fromisoformat(ts)
            except (TypeError, ValueError):
                continue
            title = self._extract_title(content)
            if title:
                parsed.append((t, title))
        return parsed

    @staticmethod
    def _extract_title(content: str) -> str:
        """Active window content is 'process.exe: Title'."""
        text = (content or "").strip()
        if not text:
            return ""
        if ": " in text:
            _, _, title = text.partition(": ")
            return title.strip()[:200]
        return text[:200]

    @staticmethod
    def _find_error_marker(text: str) -> str:
        for marker in _ERROR_MARKERS:
            if marker in text:
                return marker.rstrip(":").strip()
        return ""

    @staticmethod
    def _extract_error_preview(text: str, marker: str) -> str:
        idx = text.find(marker)
        if idx < 0:
            return ""
        start = max(0, idx - 20)
        end = min(len(text), idx + 160)
        return text[start:end].replace("\n", " ").strip()
