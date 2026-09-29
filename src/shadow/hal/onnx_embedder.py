from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer


class OnnxEmbedder:
    """Local, CPU-only sentence embedding using all-MiniLM-L6-v2 (quantized)."""

    def __init__(self, model_path: str, tokenizer_path: str):
        if not Path(model_path).exists():
            raise FileNotFoundError(
                f"Embedder model missing: {model_path}. "
                "Run: python scripts/download_embedder.py"
            )
        if not Path(tokenizer_path).exists():
            raise FileNotFoundError(
                f"Tokenizer missing: {tokenizer_path}. "
                "Run: python scripts/download_embedder.py"
            )
        so = ort.SessionOptions()
        so.intra_op_num_threads = 2
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(
            model_path, sess_options=so, providers=["CPUExecutionProvider"]
        )
        self.tokenizer = Tokenizer.from_file(tokenizer_path)
        self.tokenizer.enable_truncation(max_length=256)
        self.tokenizer.enable_padding(length=None)

    def embed(self, text: str) -> list[float]:
        enc = self.tokenizer.encode(text)
        input_ids = np.array([enc.ids], dtype=np.int64)
        attention_mask = np.array([enc.attention_mask], dtype=np.int64)
        token_type_ids = np.array([enc.type_ids], dtype=np.int64)

        outputs = self.session.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            },
        )
        # last_hidden_state: [1, seq, 384]
        token_embeddings = outputs[0]
        # mean pooling with attention mask
        mask = attention_mask[..., np.newaxis].astype(np.float32)
        summed = (token_embeddings * mask).sum(axis=1)
        counts = np.clip(mask.sum(axis=1), a_min=1e-9, a_max=None)
        mean_pooled = summed / counts
        # L2 normalize
        norm = np.linalg.norm(mean_pooled, axis=1, keepdims=True)
        normalized = mean_pooled / np.clip(norm, a_min=1e-9, a_max=None)
        return normalized[0].astype(float).tolist()
