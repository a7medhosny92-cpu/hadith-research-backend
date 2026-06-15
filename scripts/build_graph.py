"""Build the narrator network (شبكة الرواة) from the parsed corpus.

    python -m scripts.build_graph     # data/processed/*.jsonl → data/narrators.db

Parses every hadith's isnad into an ordered list of narrators and records each
adjacent تلميذ→شيخ link, aggregating across the whole corpus. The result powers
narrator exploration (/narrator) and isnad continuity checks (/verify-isnad).

Names are **unified through the رجال authority** (توحيد الاسم/الكنية/اللقب): the same man
written as a bare ism, a full nasab, a nisba, a kunya or a laqab collapses to one node.
To resolve ambiguous bare names from context, the graph is built in two passes over the
same chains: pass 1 merges only the certain cases and records each narrator's company;
pass 2 uses that company to disambiguate the rest (see :mod:`app.rijal.canon`).

Run after `scripts.parse`. Re-run anytime to rebuild (idempotent).
"""

from __future__ import annotations

import json
import time

from app.config import get_settings
from app.ingestion.catalog import RIJAL_PROSE_BOOKS
from app.parsing.jarh_extract import parse_jarh_file
from app.parsing.tahdhib_extract import parse_tahdhib_file
from app.parsing.thiqat_extract import THIQAT_BOOK_ID, parse_thiqat_file
from app.qa.isnad import analyze_isnad
from app.rijal.canon import Canonicalizer
from app.rijal.graph import NarratorGraph
from app.rijal.index import RijalIndex, _clean_tokens, load_entries
from app.rijal.muhmal import build_map as build_muhmal_map, resolve_chain, save_map as save_muhmal_map
from app.rijal.tahdhib import tahdhib_associations
from app.search.index import _read_jsonl  # parsed JSONL reader
from scripts._atomic import rebuild

# Prose رجال sources with an authoritative شيوخ/تلاميذ network, and their record extractor. Each man's
# stated company is the surest signal for disambiguating a «مشترك» name — so every prose source that
# carries a network (تهذيب · الجرح · الثقات, and later لسان/الطبقات) feeds canon._pick here.
_NETWORK_SOURCES = {3722: parse_tahdhib_file, 2170: parse_jarh_file, THIQAT_BOOK_ID: parse_thiqat_file}


def main() -> None:
    settings = get_settings()
    processed = settings.processed_dir
    files = sorted(processed.glob("*.jsonl")) if processed.exists() else []
    if not files:
        print("No parsed JSONL found. Run `python -m scripts.parse` first.")
        return
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()

    # The رجال authority (seed + full DB) drives name unification.
    rijal = RijalIndex(load_entries(settings.rijal_file))

    # Parse every isnad ONCE into a temp chains file, so the two build passes are cheap
    # reads (no re-parsing). Streaming keeps memory flat on the full corpus.
    chains_path = settings.data_dir / "_chains.tmp.jsonl"
    n_chains = 0
    with chains_path.open("w", encoding="utf-8") as fh:
        for jsonl in files:
            for rec in _read_jsonl(jsonl):
                isnad = rec.get("isnad")
                if not isnad:
                    continue
                names = [n["name"] for n in analyze_isnad(isnad).narrators]
                if len(names) >= 2:
                    fh.write(json.dumps(names, ensure_ascii=False) + "\n")
                    n_chains += 1
    print(f"Parsed {n_chains} chains from {len(files)} files")

    def read_chains():
        with chains_path.open(encoding="utf-8") as fh:
            for line in fh:
                yield json.loads(line)

    # تمييز المهمل: from the chains' own redundancy, map each (تلميذ, شيخ) context to the narrator's
    # full form, persist it for verdict time (the audit/verify load data/muhmal.json), and resolve
    # every chain's bare narrators BEFORE the graph and the profiles use them.
    muhmal = build_muhmal_map(read_chains())
    save_muhmal_map(muhmal, settings.data_dir / "muhmal.json")
    print(f"تمييز المهمل: {len(muhmal)} (تلميذ,شيخ) contexts name a bare narrator in full")

    def read_resolved():
        for ch in read_chains():
            yield resolve_chain(ch, muhmal)

    # Pass 1 — confident merges only; learn each narrator's recorded company.
    canon0 = Canonicalizer(rijal)
    g0 = NarratorGraph(":memory:")
    for ch in read_resolved():
        g0.add_chain(ch, canon=canon0)
    g0.commit()
    profiles = {
        name: set().union(*(_clean_tokens(nb) for nb in neigh)) if neigh else set()
        for name, neigh in g0.adjacency().items()
    }
    g0.close()
    print(f"Pass 1: {len(profiles)} narrators (confident merges) → context profiles")

    # …reinforced with the authoritative شيوخ/تلاميذ of the prose رجال sources on disk — al-Mizzī's
    # تهذيب الكمال and Ibn Abī Ḥātim's الجرح والتعديل (early, independent, beyond the Six Books): the
    # company each critic states per man is the surest signal for disambiguating «مشترك» names.
    for book_id, parse in _NETWORK_SOURCES.items():
        path = settings.raw_dir / "books" / f"{book_id}.json"
        if not path.exists():
            continue
        extra = tahdhib_associations(parse(path), rijal)
        for name, toks in extra.items():
            profiles.setdefault(name, set()).update(toks)
        print(f"Pass 1+: {RIJAL_PROSE_BOOKS.get(book_id, book_id)} company merged for {len(extra)} narrators")

    # …and the LLM-extracted شيوخ/تلاميذ (scripts.build_rijal_llm), if present — the network the
    # terse books don't carry. Gated, same mechanism, so absent → unchanged.
    llm_rijal = settings.data_dir / "rijal_llm.jsonl"
    if llm_rijal.exists():
        from app.rijal.llm_source import llm_associations
        extra = llm_associations(llm_rijal, rijal)
        for name, toks in extra.items():
            profiles.setdefault(name, set()).update(toks)
        print(f"Pass 1+: LLM company merged for {len(extra)} narrators")

    # Pass 2 — confident + context disambiguation, into the real DB.
    canon1 = Canonicalizer(rijal, associations=profiles)

    def build(tmp):
        graph = NarratorGraph(tmp)
        for i, ch in enumerate(read_resolved(), 1):
            graph.add_chain(ch, canon=canon1)
            if i % 5000 == 0:
                graph.commit()
                print(f"  {i}/{n_chains} chains → {graph.count()} narrators", end="\r")
        graph.commit()
        return graph

    n = rebuild(settings.narrator_graph_path, build)
    chains_path.unlink(missing_ok=True)
    print(f"\nBuilt narrator graph: {n} narrators from {n_chains} chains "
          f"(name-unified via رجال) → {settings.narrator_graph_path} in {time.time() - started:.1f}s")


if __name__ == "__main__":
    main()
