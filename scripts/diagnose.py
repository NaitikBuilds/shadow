"""Quick diagnostic for SHADOW memory + retrieval."""

import sqlite3
import sys
import traceback

import sqlite_vec

from shadow.config import load_config
from shadow.hal.cpu_backend import CpuBackend
from shadow.memory import MemoryStore
from shadow.memory.retriever import ShadowRetriever


def section(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main():
    cfg = load_config()

    section("1. Database contents")
    try:
        conn = sqlite3.connect(cfg["memory"]["db_path"])
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM observations")
        print("observations:", cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM vec_observations")
        print("vec rows:", cur.fetchone()[0])
        cur.execute(
            "SELECT id, timestamp, source, substr(content, 1, 60) FROM observations LIMIT 5"
        )
        for row in cur.fetchall():
            print("  ", row)
    except Exception:
        traceback.print_exc()

    section("2. Backend construction")
    try:
        backend = CpuBackend(
            model_path=cfg["model"]["path"],
            n_ctx=cfg["model"]["n_ctx"],
            n_threads=cfg["model"].get("n_threads") or None,
            n_gpu_layers=cfg["model"]["n_gpu_layers"],
            embedder_model=cfg["model"].get("embedder_model"),
            embedder_tokenizer=cfg["model"].get("embedder_tokenizer"),
        )
        print("backend info:", backend.info)
        print("embedder configured:", backend.embedder is not None)
    except Exception:
        traceback.print_exc()
        return

    section("3. Embedding test")
    try:
        vec = backend.embed("hello world")
        print("embedding dim:", len(vec))
        print("first 3 values:", vec[:3])
    except Exception:
        traceback.print_exc()

    section("4. Direct retrieval test")
    try:
        memory = MemoryStore(cfg["memory"]["db_path"], cfg["memory"]["vector_dim"])
        retriever = ShadowRetriever(memory, backend)
        results = retriever.semantic("what was I working on", k=3)
        print("semantic results:", len(results))
        for r in results:
            print("  ", r)
        context = retriever.context_for("what was I working on", k=3)
        print("\ncontext_for output length:", len(context))
        print("context preview:", context[:300])
    except Exception:
        traceback.print_exc()

    section("5. Direct LLM test")
    try:
        prompt = "hey??"
        out = "".join(backend.generate_stream(prompt, max_tokens=50))
        print("LLM output length:", len(out))
        print("LLM output:", repr(out[:300]))
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    main()
