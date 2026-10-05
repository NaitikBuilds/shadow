"""Tab Awareness — read and track browser and terminal tabs.

Reads the UIA tree of the active window, extracts tab titles from any
TabControl nodes, and persists first-seen timestamps so insights can
surface "this tab has been open for 8 hours and you've never visited
it" or "these three tabs are about the same topic."

Tab names live in the native tab bar chrome, so this works even when
the browser's content layer is hidden behind the screen-reader flag.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .uia import UIANode

# Words ignored when computing title overlap between tabs.
_TITLE_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "of",
    "in",
    "on",
    "at",
    "to",
    "for",
    "with",
    "by",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "should",
    "could",
    "can",
    "may",
    "might",
    "this",
    "that",
    "these",
    "those",
    "i",
    "you",
    "he",
    "she",
    "it",
    "we",
    "they",
    "my",
    "your",
    "his",
    "her",
    "its",
    "our",
    "their",
    "me",
    "him",
    "us",
    "them",
    "github",
    "chrome",
    "edge",
    "firefox",
    "brave",
    "google",
    "docs",
    "documentation",
}


@dataclass
class TabInfo:
    title: str
    is_active: bool = False
    order: int = 0

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "is_active": self.is_active,
            "order": self.order,
        }


@dataclass
class StaleTab:
    title: str
    hours_open: float
    process: str

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "hours_open": round(self.hours_open, 1),
            "process": self.process,
        }


@dataclass
class RelatedTabs:
    keyword: str
    tabs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"keyword": self.keyword, "tabs": list(self.tabs)}


class TabReader:
    """Extracts the tab list from a UIA tree."""

    def extract(self, root: UIANode | None) -> list[TabInfo]:
        """Return tab info from any TabControl nodes found in the tree."""
        if root is None:
            return []

        tabs: list[TabInfo] = []
        self._walk(root, tabs)
        # Renumber in tree order
        for i, tab in enumerate(tabs):
            tab.order = i
        return tabs

    def _walk(self, node: UIANode, out: list[TabInfo]) -> None:
        if node.control_type == "TabControl":
            for child in node.children:
                if child.control_type == "TabItemControl" and child.name:
                    out.append(
                        TabInfo(
                            title=child.name.strip()[:200],
                            is_active=child.is_selected,
                        )
                    )
        for child in node.children:
            self._walk(child, out)


class TabStateTracker:
    """Persists tab first-seen timestamps and detects patterns."""

    def __init__(self, memory):
        self.memory = memory

    # ---------- persistence ----------

    def record(self, process: str, tabs: list[TabInfo]) -> None:
        """Upsert each tab and bump last_active for the selected one."""
        if not process or not tabs:
            return

        process = process.lower().strip()
        with self.memory._lock:
            cur = self.memory.conn.cursor()
            for tab in tabs:
                if not tab.title:
                    continue
                cur.execute(
                    """
                    INSERT INTO tab_state
                        (window_process, tab_title, last_seen, last_active)
                    VALUES (?, ?, CURRENT_TIMESTAMP, ?)
                    ON CONFLICT(window_process, tab_title) DO UPDATE SET
                        last_seen = CURRENT_TIMESTAMP,
                        last_active = CASE
                            WHEN ? = 1 THEN CURRENT_TIMESTAMP
                            ELSE tab_state.last_active
                        END
                    """,
                    (
                        process,
                        tab.title,
                        1 if tab.is_active else None,
                        1 if tab.is_active else 0,
                    ),
                )
            self.memory.conn.commit()

    def prune_old(self, retention_days: int = 7) -> int:
        """Delete tabs not seen in the retention window. Returns count."""
        cutoff = (datetime.utcnow() - timedelta(days=retention_days)).isoformat(
            sep=" ", timespec="seconds"
        )
        with self.memory._lock:
            cur = self.memory.conn.cursor()
            cur.execute("DELETE FROM tab_state WHERE last_seen < ?", (cutoff,))
            deleted = cur.rowcount
            self.memory.conn.commit()
        return deleted

    # ---------- detection ----------

    def stale_tabs(
        self,
        process: str | None = None,
        stale_hours: int = 6,
    ) -> list[StaleTab]:
        """Tabs open longer than stale_hours that were never activated."""
        cutoff = (datetime.utcnow() - timedelta(hours=stale_hours)).isoformat(
            sep=" ", timespec="seconds"
        )

        try:
            cur = self.memory.conn.cursor()
            if process:
                cur.execute(
                    """
                    SELECT tab_title, window_process, first_seen
                    FROM tab_state
                    WHERE window_process = ?
                      AND first_seen < ?
                      AND last_active IS NULL
                    ORDER BY first_seen ASC
                    """,
                    (process.lower(), cutoff),
                )
            else:
                cur.execute(
                    """
                    SELECT tab_title, window_process, first_seen
                    FROM tab_state
                    WHERE first_seen < ?
                      AND last_active IS NULL
                    ORDER BY first_seen ASC
                    """,
                    (cutoff,),
                )
            rows = cur.fetchall()
        except Exception:
            return []

        now = datetime.utcnow()
        result: list[StaleTab] = []
        for title, proc, first_seen in rows:
            try:
                first = datetime.fromisoformat(first_seen)
            except (TypeError, ValueError):
                continue
            hours = (now - first).total_seconds() / 3600.0
            result.append(StaleTab(title=title, hours_open=hours, process=proc))
        return result

    def related_tabs(
        self,
        process: str | None = None,
        min_overlap: int = 2,
    ) -> list[RelatedTabs]:
        """Group tabs by shared significant words in their titles."""
        try:
            cur = self.memory.conn.cursor()
            if process:
                cur.execute(
                    "SELECT tab_title FROM tab_state " "WHERE window_process = ?",
                    (process.lower(),),
                )
            else:
                cur.execute("SELECT tab_title FROM tab_state")
            titles = [r[0] for r in cur.fetchall()]
        except Exception:
            return []

        if len(titles) < 2:
            return []

        # Tokenize each title
        title_words: dict[str, set[str]] = {}
        word_to_titles: dict[str, list[str]] = {}
        for title in titles:
            words = self._significant_words(title)
            title_words[title] = words
            for w in words:
                word_to_titles.setdefault(w, []).append(title)

        # Find words shared by >= 2 titles
        groups: list[RelatedTabs] = []
        seen_groups: set[frozenset[str]] = set()
        for word, titles_with_word in word_to_titles.items():
            if len(titles_with_word) < 2:
                continue
            key = frozenset(titles_with_word)
            if key in seen_groups:
                continue
            # Require actual overlap: at least min_overlap shared words
            # between any two titles in the group.
            if self._has_overlap(titles_with_word, title_words, min_overlap):
                seen_groups.add(key)
                groups.append(
                    RelatedTabs(
                        keyword=word,
                        tabs=sorted(titles_with_word),
                    )
                )

        # Cap and sort by group size
        groups.sort(key=lambda g: len(g.tabs), reverse=True)
        return groups[:5]

    @staticmethod
    def _significant_words(title: str) -> set[str]:
        tokens = [w.strip(".,:;!?()[]{}<>\"'").lower() for w in title.split()]
        return {w for w in tokens if len(w) >= 3 and w not in _TITLE_STOPWORDS}

    @staticmethod
    def _has_overlap(
        titles: list[str],
        title_words: dict[str, set[str]],
        min_overlap: int,
    ) -> bool:
        for i, a in enumerate(titles):
            for b in titles[i + 1 :]:
                shared = title_words[a] & title_words[b]
                if len(shared) >= min_overlap:
                    return True
        return False
