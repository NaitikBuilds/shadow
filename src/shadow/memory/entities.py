import re
from collections.abc import Iterable

# Words that look like proper nouns but aren't useful entities.
_STOPWORDS = {
    "The",
    "A",
    "An",
    "And",
    "Or",
    "But",
    "If",
    "Then",
    "So",
    "Also",
    "This",
    "That",
    "These",
    "Those",
    "It",
    "He",
    "She",
    "They",
    "We",
    "You",
    "I",
    "Us",
    "Them",
    "Me",
    "My",
    "Your",
    "Our",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
    "Today",
    "Tomorrow",
    "Yesterday",
    "Now",
    "Here",
    "There",
    "Yes",
    "No",
    "OK",
    "Okay",
    # Common OS/app chrome that OCR picks up
    "Windows",
    "File",
    "Edit",
    "View",
    "Help",
    "Settings",
    "Backend",
    "Model",
    "Threads",
    "Embedder",
}

_FILE_EXTENSIONS = (
    "py",
    "js",
    "ts",
    "tsx",
    "jsx",
    "md",
    "txt",
    "pdf",
    "docx",
    "json",
    "yaml",
    "yml",
    "toml",
    "sql",
    "html",
    "css",
    "sh",
    "ps1",
    "bat",
    "csv",
    "log",
    "ini",
)


class EntityExtractor:
    """Rule-based entity extraction from observation text.

    Fast, deterministic, offline. No LLM involved.
    """

    _CAP_PHRASE = re.compile(r"\b([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){0,2})\b")
    _FILE_NAME = re.compile(r"\b([\w\-]+\.(?:" + "|".join(_FILE_EXTENSIONS) + r"))\b")

    def __init__(self, known_projects: Iterable[str] = ()):
        self.known_projects = {
            p.strip().lower(): p.strip() for p in known_projects if p.strip()
        }

    def extract(self, text: str) -> list[dict]:
        """Return [{type, name}] entities found in text, deduplicated."""
        if not text:
            return []

        found: dict[tuple[str, str], dict] = {}

        # 1. Known projects (case-insensitive substring match)
        lower = text.lower()
        for key, original in self.known_projects.items():
            if key in lower:
                found[("project", original)] = {"type": "project", "name": original}

        # 2. Capitalized phrases → topics
        for match in self._CAP_PHRASE.finditer(text):
            cleaned = self._clean_topic(match.group(1).strip())
            if cleaned is None:
                continue
            found.setdefault(("topic", cleaned), {"type": "topic", "name": cleaned})

        # 3. Filenames → files
        for match in self._FILE_NAME.finditer(text):
            name = match.group(1)
            found[("file", name)] = {"type": "file", "name": name}

        return list(found.values())

    @staticmethod
    def _clean_topic(name: str) -> str | None:
        """Return a cleaned topic name, or None if nothing usable remains."""
        tokens = [t for t in name.split() if t not in _STOPWORDS]
        if not tokens:
            return None
        cleaned = " ".join(tokens)
        if len(cleaned) < 3:
            return None
        # All-caps acronyms (SHADOW, SQL, ONNX) are valid
        if cleaned.isupper() and len(cleaned) >= 2:
            return cleaned
        first = tokens[0]
        if len(first) < 3:
            return None
        if first[0].isdigit():
            return None
        return cleaned


class GraphBuilder:
    """Populates the knowledge graph from a single observation.

    Combines entity extraction with upsert, linking, and co-occurrence edges.
    """

    def __init__(self, memory, extractor: EntityExtractor):
        self.memory = memory
        self.extractor = extractor

    def process(self, observation_id: int, content: str) -> int:
        """Extract entities, link to observation, add co-occurrence edges.

        Returns the number of entities linked to the observation.
        """
        entities = self.extractor.extract(content)
        if not entities:
            return 0

        entity_ids: list[int] = []
        for e in entities:
            try:
                eid = self.memory.upsert_entity(e["type"], e["name"])
            except ValueError:
                continue
            self.memory.link_entity_to_observation(observation_id, eid)
            entity_ids.append(eid)

        # Co-occurrence edges: each unordered pair gets a bidirectional
        # weak edge. Weight accumulates across observations.
        for i, a in enumerate(entity_ids):
            for b in entity_ids[i + 1 :]:
                self.memory.add_edge(a, b, "co_occurs", weight=0.1)
                self.memory.add_edge(b, a, "co_occurs", weight=0.1)

        return len(entity_ids)
