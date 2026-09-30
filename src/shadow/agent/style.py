"""Style Mirror — generate text matching the user's own writing style.

Reads style samples from past document observations, uses them as
few-shot examples in the LLM prompt, and (when the embedder is
available) checks the generated output for style similarity.

No new permissions. Reads only existing observations.
"""

from dataclasses import dataclass

from .prompt_builder import PromptBuilder


@dataclass
class StyleResult:
    text: str
    style_score: float | None
    sample_count: int
    low_confidence: bool


class StyleMirrorEngine:
    """Generates text that sounds like the user."""

    MIN_SAMPLE_CHARS = 100
    MAX_SAMPLE_CHARS = 1500
    STYLE_CORPUS_SIZE = 3
    SIMILARITY_GATE = 0.82

    def __init__(self, memory):
        self.memory = memory
        self.prompt_builder = PromptBuilder()

    # ---------- public API ----------

    def sample_style(self, n: int | None = None) -> list[str]:
        """Fetch style samples from recent document observations."""
        n = n or self.STYLE_CORPUS_SIZE
        try:
            cur = self.memory.conn.cursor()
            cur.execute(
                "SELECT content FROM observations "
                "WHERE source = 'document' "
                "ORDER BY timestamp DESC LIMIT 30"
            )
            rows = cur.fetchall()
        except Exception:
            return []

        samples: list[str] = []
        for (content,) in rows:
            text = (content or "").strip()
            # Strip "Document: filename\n" prefix if present
            if text.startswith("Document:"):
                nl = text.find("\n")
                if nl >= 0:
                    text = text[nl + 1 :]
            text = text.strip()
            if len(text) < self.MIN_SAMPLE_CHARS:
                continue
            samples.append(text[: self.MAX_SAMPLE_CHARS])
            if len(samples) >= n:
                break
        return samples

    def generate(
        self,
        user_request: str,
        backend,
        max_tokens: int = 256,
        check_similarity: bool = True,
    ) -> StyleResult:
        """Generate text in the user's style.

        Args:
            user_request: what to write, e.g. "reply declining a meeting".
            backend: the inference backend.
            max_tokens: LLM token cap.
            check_similarity: whether to compute the style score.
        """
        samples = self.sample_style()
        if not samples:
            # No style data yet — fall back to plain generation
            text = "".join(
                backend.generate_stream(user_request, max_tokens=max_tokens)
            ).strip()
            return StyleResult(
                text=text,
                style_score=None,
                sample_count=0,
                low_confidence=True,
            )

        prompt = self._build_style_prompt(user_request, samples)
        text = "".join(backend.generate_stream(prompt, max_tokens=max_tokens)).strip()

        score: float | None = None
        low = False
        if check_similarity:
            try:
                score = self._similarity(text, samples, backend)
                low = score < self.SIMILARITY_GATE
            except Exception:
                score = None
                low = False

        return StyleResult(
            text=text,
            style_score=score,
            sample_count=len(samples),
            low_confidence=low,
        )

    # ---------- internals ----------

    def _build_style_prompt(self, user_request: str, samples: list[str]) -> str:
        header = (
            "Write the following in the style of the examples below. "
            "Match tone, sentence length, vocabulary, and rhythm. "
            "Do not copy phrases verbatim."
        )
        parts = [header, ""]
        for i, sample in enumerate(samples, 1):
            parts.append(f"--- Example {i} ---")
            parts.append(sample)
            parts.append("")
        parts.append("--- Task ---")
        parts.append(self.prompt_builder._clean(user_request))
        return "\n".join(parts)

    def _similarity(self, text: str, samples: list[str], backend) -> float:
        """Cosine similarity between generated text and style corpus mean."""
        import numpy as np

        if not text.strip():
            return 0.0
        try:
            gen_vec = np.array(backend.embed(text), dtype=float)
        except Exception:
            return 0.0

        sample_vecs = []
        for s in samples:
            try:
                sample_vecs.append(np.array(backend.embed(s), dtype=float))
            except Exception:
                continue
        if not sample_vecs:
            return 0.0

        mean_vec = np.mean(sample_vecs, axis=0)
        denom = np.linalg.norm(gen_vec) * np.linalg.norm(mean_vec)
        if denom <= 0:
            return 0.0
        return float(np.dot(gen_vec, mean_vec) / denom)
