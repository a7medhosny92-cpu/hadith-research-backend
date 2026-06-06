"""Build the narrator network (شبكة الرواة) from the parsed corpus.

    python -m scripts.build_graph     # data/processed/*.jsonl → data/narrators.db

Parses every hadith's isnad into an ordered list of narrators and records each
adjacent تلميذ→شيخ link, aggregating across the whole corpus. The result powers
narrator exploration (/narrator) and isnad continuity checks (/verify-isnad).

Run after `scripts.parse`. Re-run anytime to rebuild (idempotent).
"""

from __future__ import annotations

import time

from app.config import get_settings
from app.qa.isnad import analyze_isnad
from app.rijal.graph import NarratorGraph
from app.search.index import _read_jsonl  # parsed JSONL reader
from scripts._atomic import rebuild


def main() -> None:
    settings = get_settings()
    processed = settings.processed_dir
    files = sorted(processed.glob("*.jsonl")) if processed.exists() else []
    if not files:
        print("No parsed JSONL found. Run `python -m scripts.parse` first.")
        return
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    stats = {"chains": 0, "hadith": 0}

    def build(tmp):
        graph = NarratorGraph(tmp)
        for jsonl in files:
            for rec in _read_jsonl(jsonl):
                isnad = rec.get("isnad")
                if not isnad:
                    continue
                stats["hadith"] += 1
                names = [n["name"] for n in analyze_isnad(isnad).narrators]
                if len(names) >= 2:
                    graph.add_chain(names)
                    stats["chains"] += 1
                if stats["hadith"] % 5000 == 0:
                    graph.commit()
                    print(f"  {stats['hadith']} isnads → {graph.count()} narrators", end="\r")
        graph.commit()
        return graph

    n = rebuild(settings.narrator_graph_path, build)
    print(f"\nBuilt narrator graph: {n} narrators from {stats['chains']} chains "
          f"→ {settings.narrator_graph_path} in {time.time() - started:.1f}s")


if __name__ == "__main__":
    main()
