"""Dump the raw text of the empty-matn hadith (the «تدقيق المتون» V cases) so the isnad/matn
split can be diagnosed — for each one the matn came out EMPTY, so the `isnad` column holds the
WHOLE original text (isnad + the matn that was wrongly swallowed into it).

For every example it prints which boundary markers `split_isnad_matn` *can* see (INTRO «قال:» /
SAY «قال» / ANNA «أنّ النبيّ» / a bare «أنّ» / TRANSMIT) and what the current code does — so we see
exactly why no matn boundary fired. Read-only; touches only `index.db`.

    python -m scripts.peek_matn                 # ~3 empty-matn examples per collection
    python -m scripts.peek_matn --per 5         # N examples per collection
    python -m scripts.peek_matn --tail 0        # print the FULL text (not just its tail)
"""

from __future__ import annotations

import argparse
import sqlite3

from app.config import get_settings
from app.parsing.isnad_matn import (
    split_isnad_matn, _INTRO, _SAY, _ANNA, _ANNA_WORD, _TRANSMIT,
)

_EMPTY = "trim(isnad) <> '' AND (matn IS NULL OR length(trim(matn)) = 0)"


def _markers(text: str) -> str:
    out = []
    if _INTRO.search(text): out.append("INTRO«قال:»")
    if _SAY.search(text): out.append("SAY«قال»")
    if _ANNA.search(text): out.append("ANNA«أنّ النبيّ»")
    if _ANNA_WORD.search(text): out.append("«أنّ»")
    if _TRANSMIT.search(text): out.append("TRANSMIT")
    return "، ".join(out) or "NONE"


def main() -> None:
    ap = argparse.ArgumentParser(description="Dump empty-matn hadith to diagnose the isnad/matn split.")
    ap.add_argument("--per", type=int, default=3, help="examples per collection")
    ap.add_argument("--tail", type=int, default=320, help="print only the last N chars (0 = full text)")
    args = ap.parse_args()

    con = sqlite3.connect(str(get_settings().index_path))
    colls = con.execute(
        f"SELECT collection, COUNT(*) c FROM hadith WHERE {_EMPTY} GROUP BY collection ORDER BY c DESC"
    ).fetchall()
    print("متونٌ فارغة لكلّ مصدر (الأكثر أولًا):")
    for coll, c in colls:
        print(f"  {c:>5}  {coll}")
    print()

    for coll, _c in colls:
        rows = con.execute(
            f"SELECT number, isnad FROM hadith WHERE collection = ? AND {_EMPTY} ORDER BY rowid LIMIT ?",
            (coll, args.per),
        ).fetchall()
        for num, isnad in rows:
            _iz, mt, conf = split_isnad_matn(isnad)
            text = isnad.strip()
            shown = text if args.tail <= 0 or len(text) <= args.tail else "…" + text[-args.tail:]
            print(f"═══ {coll} · رقم {num} · split={conf} · matn_now={len(mt)} · markers: {_markers(isnad)} ═══")
            print(shown)
            print()
    con.close()


if __name__ == "__main__":
    main()
