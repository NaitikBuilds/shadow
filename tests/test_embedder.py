import os
from pathlib import Path

import pytest

MODEL = Path("models/minilm/model.onnx")
TOK = Path("models/minilm/tokenizer.json")


@pytest.mark.skipif(not MODEL.exists() or not TOK.exists(),
                    reason="embedder not downloaded")
def test_embedder_dim_and_similarity():
    from shadow.hal.onnx_embedder import OnnxEmbedder

    e = OnnxEmbedder(str(MODEL), str(TOK))
    a = e.embed("I love coffee in the morning.")
    b = e.embed("Coffee helps me focus.")
    c = e.embed("Quantum chromodynamics is a theory.")

    assert len(a) == 384

    def cos(x, y):
        import numpy as np
        x, y = np.array(x), np.array(y)
        return float(x @ y / (np.linalg.norm(x) * np.linalg.norm(y)))

    assert cos(a, b) > cos(a, c)