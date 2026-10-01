"""Intent-Aware Notes — auto-capture "note to self" phrases.

Scans recent observations for natural-language intent triggers
("remind me to", "don't forget", "I need to") and surfaces them
as structured insights. The user decides whether to actually
save them as notes.

No new tables. Reads on demand.
"""

import hashlib
import re
from datetime import datetime, timedelta

from .insight import Insight

# Trigger phrases. Ordered by specificity (longest first) so the
# extractor prefers "note to self" over a bare "note".
TRIGGERS = (
    "note to self",
    "don't forget",
    "dont forget",
    "remind me to",
    "remember to",
    "i need to",
    "i should",
    "todo:",
    "task:",
)

LOOKBACK_HOURS = 24
MIN_ACTION_CHARS = 4
MAX_ACTION_CHARS = 200


# Pre-compile a pattern that matches any trigger at a word boundary.
_TRIGGER_PATTERN = re.compile(
    r"(?i)\b(" + "|".join(re.escape(t) for t in TRIGGERS) + r")\b[:,]?\s*"
)


class IntentNotesEngine:
    """Extracts intent phrases from recent observations."""

    def __init__(self, memory):
        self.memory = memory

    # ---------- public API ----------

    def find_notes(self, limit: int = 5) -> list[Insight]:
        rows = self._recent_observations()
        if not rows:
            return []

        seen: set[str] = set()
        insights: list[Insight] = []

        for row in rows:
            for phrase, action in self._extract_intents(row["content"]):
                normalized = self._normalize(action)
                if len(normalized) < MIN_ACTION_CHARS:
                    continue
                key = hashlib.sha1(normalized.encode()).hexdigest()[:12]
                if key in seen:
                    continue
                seen.add(key)
                insights.append(self._build_insight(phrase, action, row))
                if len(insights) >= limit:
                    return insights

        return insights

    # ---------- internals ----------

    def _recent_observations(self) -> list[dict]:
        cutoff = (datetime.utcnow() - timedelta(hours=LOOKBACK_HOURS)).isoformat(
            sep=" ", timespec="seconds"
        )

        try:
            cur = self.memory.conn.cursor()
            cur.execute(
                "SELECT id, timestamp, source, content FROM observations "
                "WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT 200",
                (cutoff,),
            )
            raw = cur.fetchall()
        except Exception:
            return []

        rows: list[dict] = []
        for obs_id, ts, source, content in raw:
            try:
                parsed = datetime.fromisoformat(ts)
            except (TypeError, ValueError):
                continue
            rows.append(
                {
                    "id": obs_id,
                    "timestamp": parsed,
                    "source": source,
                    "content": content or "",
                }
            )
        return rows

    @staticmethod
    def _extract_intents(text: str) -> list[tuple[str, str]]:
        """Return [(trigger, action)] for each intent phrase found."""
        found: list[tuple[str, str]] = []
        for match in _TRIGGER_PATTERN.finditer(text):
            phrase = match.group(1).lower()
            # Grab the rest of the sentence after the trigger
            tail_start = match.end()
            tail = text[tail_start:]
            # Stop at sentence end
            end = min(
                [
                    i
                    for i in (
                        tail.find("."),
                        tail.find("!"),
                        tail.find("?"),
                        tail.find("\n"),
                    )
                    if i >= 0
                ]
                or [len(tail)]
            )
            action = tail[:end].strip()
            action = action[:MAX_ACTION_CHARS]
            if action:
                found.append((phrase, action))
        return found

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.lower().split())

    def _build_insight(self, phrase: str, action: str, row: dict) -> Insight:
        preview = action[:140]
        return Insight(
            kind="intent_note",
            title="Note to self",
            body=f'You mentioned: "{preview}"',
            score=0.6,
            action="Save as note",
            bypass_focus_shield=True,
        )
