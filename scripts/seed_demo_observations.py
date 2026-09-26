"""Seed a few observations for local testing of semantic/temporal query."""

from datetime import datetime, timedelta

from shadow.config import load_config
from shadow.hal.cpu_backend import CpuBackend
from shadow.memory import MemoryStore

cfg = load_config()
backend = CpuBackend(
    model_path=cfg["model"]["path"],
    n_ctx=cfg["model"]["n_ctx"],
    n_threads=cfg["model"].get("n_threads") or None,
    n_gpu_layers=cfg["model"]["n_gpu_layers"],
    embedder_model=cfg["model"].get("embedder_model"),
    embedder_tokenizer=cfg["model"].get("embedder_tokenizer"),
)
store = MemoryStore(cfg["memory"]["db_path"], cfg["memory"]["vector_dim"])

samples = [
    ("screen", "Working on SHADOW Phase 1 — consent and memory."),
    ("note", "Idea: Shadow should be able to recall what I was doing last week."),
    ("screen", "Reading about sqlite-vec for local semantic search."),
    ("note", "Reminder: finish the Privacy Dashboard before Phase 2."),
    ("screen", "Debugging ONNX embedder loading all-MiniLM-L6-v2."),
]

for source, text in samples:
    rid = store.add_observation(source, text)
    store.add_embedding(rid, backend.embed(text))

# Add one intentionally older observation for temporal tests.
old_ts = (datetime.utcnow() - timedelta(days=10)).isoformat(sep=" ", timespec="seconds")
cur = store.conn.cursor()
cur.execute(
    "INSERT INTO observations (timestamp, source, content) VALUES (?, ?, ?)",
    (old_ts, "note", "Last month I was researching intention forecasting."),
)
old_id = cur.lastrowid
cur.execute(
    "INSERT INTO vec_observations (rowid, embedding) VALUES (?, ?)",
    (
        old_id,
        __import__("sqlite_vec").serialize_float32(
            backend.embed("Last month I was researching intention forecasting.")
        ),
    ),
)
store.conn.commit()

print("Seeded", len(samples) + 1, "observations.")
store.close()
