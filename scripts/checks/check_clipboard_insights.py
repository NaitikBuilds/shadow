"""Check what the ClipboardActionsEngine actually returns right now."""

from shadow.agent import ClipboardActionsEngine
from shadow.config import load_config
from shadow.memory import MemoryStore

cfg = load_config()
store = MemoryStore(cfg["memory"]["db_path"])
try:
    engine = ClipboardActionsEngine(store)
    print("lookback window:", engine.LOOKBACK_MIN, "minutes")

    rows = engine._recent_clipboard()
    print("rows found in window:", len(rows))
    for r in rows:
        print("  id:", r[0], "ts:", r[1], "preview:", (r[2] or "")[:60])

    print()
    insights = engine.suggest()
    print("insights returned:", len(insights))
    for i in insights:
        print(f"  [{i.kind}] {i.title} (score {i.score})")
        print(f"    {i.body[:100]}")
finally:
    store.close()
