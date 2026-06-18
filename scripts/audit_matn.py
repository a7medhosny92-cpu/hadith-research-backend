"""Audit every matn for likely extraction errors across the whole corpus.

The متن counterpart of ``scripts.audit_isnad``: it scans every ḥadīth in ``index.db`` through
``app.parsing.matn_audit.flag_matn`` and writes ``{DATA_DIR}/matn_audit.json`` for the in-app
«تدقيق المتون» review tab (each hit a candidate for a human / the LLM repair pass, not a verdict).

    python -m scripts.audit_matn               # scan all, write the report, print a summary
    python -m scripts.audit_matn --limit 2000  # scan only the first N (faster)
    python -m scripts.audit_matn --cap 800     # keep up to N cases per category in the report

Run after building the index (``scripts.index``); ``update.bat`` runs it as a step.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections import Counter

from app.config import get_settings
from app.parsing.matn_audit import LABELS, flag_matn


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit matn extraction for likely errors.")
    ap.add_argument("--limit", type=int, default=None, help="scan only the first N hadith")
    ap.add_argument("--cap", type=int, default=500, help="cases to keep per category in the report")
    args = ap.parse_args()

    settings = get_settings()
    con = sqlite3.connect(str(settings.index_path))
    sql = "SELECT rowid, collection, number, matn, isnad, chapter FROM hadith WHERE kind = 'hadith'"
    if args.limit:
        sql += f" LIMIT {args.limit}"
    rows = con.execute(sql).fetchall()
    con.close()
    total = len(rows)
    print(f"scanning {total} matns…", flush=True)

    counts: Counter[str] = Counter()
    cases: dict[str, list[dict]] = {c: [] for c in LABELS}
    empty = 0
    for rid, coll, num, matn, isnad, chapter in rows:
        if not (matn or "").strip():
            empty += 1
        for code, detail in flag_matn(matn or "", isnad or "", chapter or ""):
            counts[code] += 1
            if len(cases[code]) < args.cap:
                cases[code].append({"id": rid, "collection": coll, "number": num,
                                    "detail": detail, "matn": (matn or "")[:160]})

    report = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "scanned": total,
        "empty_matn": empty,
        "counts": {c: counts[c] for c in LABELS},
        "labels": LABELS,
        "cases": cases,
    }
    out_path = settings.data_dir / "matn_audit.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

    print(f"\nscanned {total} matns → {out_path}")
    for code in LABELS:
        print(f"  [{code}] {LABELS[code]}: {counts[code]}")
    print(f"  (empty matns overall: {empty})")


if __name__ == "__main__":
    main()
