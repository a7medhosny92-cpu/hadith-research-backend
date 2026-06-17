"""Probe سير أعلام النبلاء (الذهبي, ط الرسالة, 10906) for writing its extractor — read-only.

سير is a biographical طبقات dictionary: after a long preamble (the محقق's muqaddima + the السيرة
النبوية + the الخلفاء الراشدون), every notable man gets a numbered tarjama whose HEADING is
«N - Name nasab» (the same shape as الثقات/لسان), BUT the numbers **restart at ١ each طبقة** and
`indexes.numbers` is empty — so the tarjama can't be keyed by number (الثقات's trick). The boundary
that DOES work is the body's line-start «N - » run (rijal_extract._BOUNDARY), with the name read from
the body head (الجرح's trick), so this dumps exactly what the extractor must be designed against:

  1) `indexes.headings` around the preamble→tarjama transition (to see the «N - Name» heads + levels);
  2) the line-start «N - » boundary count;
  3) FULL tarjama bodies from the START (to find the preamble→tarjama boundary + the junk to filter),
     the MIDDLE (تابعون/أتباع), and the LATE quarter (the post-Six-Books محدّثون — الأصم-class, whose
     «حدّث عن … حدّث عنه …» network is the A.3 coverage lever) — so the name / network markers /
     verdict / «مات سنة …» format is visible verbatim across طبقات.

Writes `sair_struct.txt` (clean UTF-8) to upload.

    python -m scripts.peek_sair
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.config import get_settings
from app.parsing.html_clean import clean_block
from app.parsing.rijal_extract import _BOUNDARY

SAIR_BOOK_ID = 10906
_BODY_CAP = 900          # chars of each tarjama body to dump (سير tarajim are long)
_HEAD_FROM, _HEAD_TO = 165, 215   # headings window over the preamble→tarjama transition
_N = 6                   # bodies to dump from each of START / MIDDLE / LATE


def main() -> None:
    path = get_settings().raw_dir / "books" / f"{SAIR_BOOK_ID}.json"
    if not path.exists():
        print(f"{SAIR_BOOK_ID}.json not found under {path.parent} — make sure سير is downloaded.")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    lines: list[str] = [f"# سير أعلام النبلاء {SAIR_BOOK_ID} — {len(data.get('pages', []))} pages\n"]

    headings = (data.get("indexes") or {}).get("headings") or []
    nums = (data.get("indexes") or {}).get("numbers") or {}
    lines.append(f"=== indexes.headings: {len(headings)} | indexes.numbers: {len(nums)} ===")
    lines.append(f"--- headings[{_HEAD_FROM}:{_HEAD_TO}] (the preamble→tarjama transition) ---")
    for h in headings[_HEAD_FROM:_HEAD_TO]:
        t = re.sub(r"\s+", " ", h.get("title") or "").strip()
        lines.append(f"  p{h.get('page')!s:>5} L{h.get('level')}  {t[:70]}")

    pages = sorted(data.get("pages", []), key=lambda p: p.get("page", p.get("pg", 0)))
    full = "\n".join(clean_block(p.get("text") or "") for p in pages)

    bounds = [m for m in _BOUNDARY.finditer(full) if m.group(1) is not None]
    lines.append(f"\n=== {len(bounds)} line-start «N -» boundaries ===")

    def dump(idx: int) -> None:
        m = bounds[idx]
        end = bounds[idx + 1].start() if idx + 1 < len(bounds) else len(full)
        body = re.sub(r"[ \t]+", " ", full[m.end(): end]).strip()
        lines.append(f"\n── «{m.group(1)} -» (boundary {idx}) ──")
        lines.append(body[:_BODY_CAP])

    n = len(bounds)
    for label, base in (("FIRST (preamble → first tarjamas)", 0),
                        ("MIDDLE (تابعون/أتباع)", n // 2),
                        ("LATE quarter (post-Six-Books محدّثون — the A.3 network)", (3 * n) // 4)):
        lines.append(f"\n========== {_N} bodies — {label} ==========")
        for i in range(base, min(base + _N, n)):
            dump(i)

    out = "\n".join(lines)
    Path("sair_struct.txt").write_text(out, encoding="utf-8")
    print(f"wrote sair_struct.txt ({len(out)} chars) — upload it (Drive `data` folder is fine)")


if __name__ == "__main__":
    main()
