from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Insight:
    """A single proactive observation SHADOW surfaces to the user.

    Every Phase 3+ feature produces Insight objects. The panel renders
    them uniformly without knowing which engine created them.
    """

    kind: str
    title: str
    body: str
    score: float = 0.5
    action: str = ""
    entity_id: int | None = None
    created_at: str = field(
        default_factory=lambda: datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    )

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "title": self.title,
            "body": self.body,
            "score": self.score,
            "action": self.action,
            "entity_id": self.entity_id,
            "created_at": self.created_at,
        }
