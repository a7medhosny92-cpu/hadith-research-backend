"""Extract narrator records from سير أعلام النبلاء (الذهبي, ط الرسالة, 10906).

A COVERAGE source covering post-Six-Books men (الأصم-class محدّثون, 5th–8th centuries). Like الجرح/الثقات,
it is a PROSE rijal dictionary with documented شيوخ/تلاميذ network — the key for joint-resolver disambiguation.

**Segmentation (page-driven, like isaba_extract — never drops a tarjama).** سير's body is continuous prose
whose tarjama markers «N -» are NOT reliably line-anchored — the line-start `rijal_extract._BOUNDARY` caught
only 432 of ~5893 (≈7 %), so a body-boundary extractor missed almost every man, esp. the LATE الأصم-class
(the whole point of the source). The reliable structure is `indexes.headings`: every tarjama IS a heading
«N - Name» carrying its **page** (numbers RESTART each طبقة and `indexes.numbers` is empty, so the page —
not the number — is the key). So the headings are walked in order and each is mapped to its body by PAGE: a
heading's body runs from its page to the next heading's page, and several short tarjamas sharing one page are
sub-split by locating each heading's name. Every «N - Name» heading therefore yields a record.

The name comes from the (clean) heading; the body gives the network «حدّث عن … حدّث عنه …» / «وعنه …», the
death «مات سنة …», and the quoted جرح/تعديل critics. Grade = weakest cited verdict, else «غير معروف»
(coverage pattern: no inclusion توثيق like الثقات, so no default «ثقة»).
"""

from __future__ import annotations

import bisect
import json
import re
from pathlib import Path
from typing import Iterator

from app.parsing.appraisals import extract_appraisals
from app.parsing.html_clean import arabic_digits_to_int, clean_block
from app.parsing.jarh_extract import (
    _KUNYA,
    _block_between,
    _names,
    _verdicts,
)
from app.parsing.normalize import strip_diacritics
from app.parsing.rijal_extract import _death_year
from app.rijal.grades import classify

SAIR_BOOK_ID = 10906
_SOURCE = "سير أعلام النبلاء (الذهبي، ط الرسالة، رقم 10906)"

_WS = re.compile(r"\s+")
_FOOTNOTE = re.compile(r"_{4,}")
_EDIT = re.compile(r"\[[^\]]*\]|\([^)]*\)")
# سير's network markers (verified on the real book's LATE الأصم-class tarjamas): شيوخ by «حدّث عن» /
# «روى عن», تلاميذ by «حدّث/روى عنه» AND — the dominant form — the bare «وعنه». Missing «وعنه» dropped
# most تلاميذ AND (since it ends the شيوخ block) leaked the students into the teachers.
_SHU_SAIR = re.compile(r"(?:حدّ?ث|رو[ىي])\s+عن(?!ه)")
_TAL_SAIR = re.compile(r"(?:حدّ?ث\s+عنه|رو[ىي]\s+عنه|وعنه)")
# Where a network block ends: a transmission/speech verb, a death, a verdict verb («ضعّفه/وثّقه»), or a
# list-terminator («وآخرون/وخلق/وجماعة») — سير closes a تلاميذ list with these BEFORE the critics' verdicts,
# so this keeps a cited critic (أبو حاتم…) from being read as a تلميذ.
_NET_END = re.compile(
    r"سمعت|حدثنا|أخبرنا|أنبأنا|قال|سئل|مات|توفي|قاله|يقال|ذكره|قلت|"
    r"ضعّفه|ضعفه|وثّقه|وثقه|آخرون|وجماعة|وخلق|وغيرهم"
)
# A «N - Name» tarjama heading (in indexes.headings) — «١٤٥ - عمرو بن دينار البصري».
_HEAD = re.compile(r"^\s*([\d٠-٩۰-۹]+)\s*[-–—]\s*(.+)$")
# Name boundary: where tarjama body text begins (network markers, transmission verbs, verdict/death).
_NAME_END = re.compile(
    r"حدّ?ث|رو[ىي]\s+عنه?|سمعت|أخبرنا|أنبأنا|قال|يقال|مات|توفي|كان|وكان|ذكره|وفي|بل|إن|لكن"
)
_JUNK_HEAD = ("باب", "كتاب", "فصل", "ذكر", "مقدمة", "فأما", "وأما", "أخوه", "وابنه", "ابنه")
_PAGE_SLACK = 4  # search a name a few chars before the page start (heading may sit on the prior line)
# سير is biographical PROSE peppered with stories/dialogue, so `_verdicts` captures a SPEECH «قال له: …»
# whose body is a narrated taunt, not a جرح — «ما يسمونك إلا الكذّاب»، «جئتَ تسمعُ؟ … لا تلقى إلا كذّاب»
# graded نفيع أبو رافع الصائغ (ثقة) and صدقة (ضعيف) «كذّاب». A captured verdict carrying a 2nd-person /
# question / vocative marker is reported speech (a scene), dropped before grading; a terse critic verdict
# («ضعيف»، «كذّبه أبو حاتم»، «ثقة») has none and is kept → coverage falls back to «غير معروف», never a false كذّاب.
_NARRATIVE = re.compile(r"يسمونك|يسمّونك|إنك|انك|أنت|انت|جئت|تسمع|سمعتَ|يا\s|؟")


def _clean_name(raw: str) -> str | None:
    """Extract a clean name from a raw tarjama head, stopping at a network/verdict marker."""
    name = _EDIT.sub(" ", raw)
    name = _NAME_END.split(name, 1)[0]
    name = _WS.sub(" ", name).strip(" .،:-—*")
    return name if len(name.split()) >= 2 else None


def _grade_from(verdicts: list[str]) -> str:
    """The rijal grade: WEAKEST cited جرح/تعديل verdict (الجرح المفسَّر مقدَّم), else «غير معروف»
    (coverage pattern: no inclusion توثيق like الثقات, so no default «ثقة»)."""
    graded = [(rank, v) for v in verdicts if (rank := classify(v)[1]) is not None]
    return min(graded, key=lambda g: g[0])[1] if graded else "غير معروف"


def book_main_text(data: dict) -> str:
    """Full cleaned text of the book, skipping footnotes (editor's notes on «____» boundaries)."""
    pages = sorted(data.get("pages", []), key=lambda p: p.get("pg", 0))
    return "\n".join(
        _FOOTNOTE.split(clean_block(p.get("text") or ""), 1)[0] for p in pages
    )


def _tarjama_heads(data: dict) -> list[tuple[int, int, str]]:
    """Ordered ``(page, number, name)`` for every «N - Name» heading — the reliable tarjama list.

    The page (not the number, which restarts each طبقة) is what locates the body."""
    out: list[tuple[int, int, str]] = []
    for h in (data.get("indexes") or {}).get("headings") or []:
        m = _HEAD.match(_WS.sub(" ", h.get("title") or "").strip())
        if not m:
            continue
        num, name, pg = arabic_digits_to_int(m.group(1)), _clean_name(m.group(2)), h.get("page")
        if num and name and pg is not None and not name.startswith(_JUNK_HEAD):
            out.append((int(pg), num, name))
    return out


def _locate(stripped: str, name: str, frm: int, to: int) -> int:
    """First offset of the name (its first ≤4 leading tokens) within ``stripped[frm:to]``, else ``-1``."""
    toks = strip_diacritics(name).split()
    for k in (4, 3, 2):
        if len(toks) >= k:
            idx = stripped.find(" ".join(toks[:k]), frm, to)
            if idx >= 0:
                return idx
    return -1


def _segment(data: dict) -> Iterator[tuple[int, str, str]]:
    """Walk the heading list and yield ``(number, name, body)`` for every «N - Name» tarjama.

    Each heading is mapped to its body by PAGE: the body runs from this heading's located position to the
    next heading's — several short tarjamas on one page are sub-split by locating each name, and a heading
    whose name cannot be located still gets the page span (so a tarjama is never dropped)."""
    heads = _tarjama_heads(data)
    if not heads:
        return
    pages = sorted(
        (
            (p["pg"], _FOOTNOTE.split(clean_block(p.get("text") or ""), 1)[0])
            for p in data.get("pages", [])
            if p.get("pg") is not None
        ),
        key=lambda x: x[0],
    )
    if not pages:
        return
    page_start: dict[int, int] = {}
    page_end: dict[int, int] = {}
    parts: list[str] = []
    off = 0
    for pg, text in pages:
        page_start[pg] = off
        parts.append(text)
        off += len(text) + 1
        page_end[pg] = off - 1
    full = "\n".join(parts)
    stripped = strip_diacritics(full)
    pgs = [pg for pg, _ in pages]

    starts: list[int] = []
    cursor: dict[int, int] = {}
    for pg, _num, name in heads:
        if pg in page_start:
            base, pend = page_start[pg], page_end[pg]
        else:                                              # heading page not an exact page id → nearest ≤ pg
            i = bisect.bisect_right(pgs, pg) - 1
            if i < 0:
                starts.append(-1)
                continue
            base, pend = page_start[pgs[i]], page_end[pgs[i]]
        frm = max(base - _PAGE_SLACK, cursor.get(pg, base - _PAGE_SLACK))
        pos = _locate(stripped, name, max(0, frm), pend)
        if pos < 0:
            pos = max(0, frm)
        starts.append(pos)
        cursor[pg] = pos + 1

    n = len(heads)
    for i, (_pg, num, name) in enumerate(heads):
        s = starts[i]
        if s < 0:
            continue
        e = len(full)
        for j in range(i + 1, n):
            if starts[j] > s:
                e = starts[j]
                break
        yield num, name, full[s:e]


def parse_entry(number: int | None, body: str, heading_name: str | None = None) -> dict | None:
    """One tarjama → a graded record, or ``None`` for junk / non-narrator entries. The name is taken
    from the (clean) ``heading_name`` when given, else read from the body head."""
    body = _WS.sub(" ", body).strip()
    if len(body) < 8:
        return None
    name = heading_name or _clean_name(body)
    if not name or name.startswith(_JUNK_HEAD):
        return None
    # Network, verdicts, death year.
    shuyukh = _names(_block_between(body, _SHU_SAIR, _TAL_SAIR, _NET_END))
    talamidh = _names(_block_between(body, _TAL_SAIR, _NET_END))
    verdicts = [v for v in _verdicts(body) if not _NARRATIVE.search(v)]   # drop reported-speech «scenes»
    record: dict = {"number": number, "name": name, "grade": _grade_from(verdicts), "source": _SOURCE}
    kunya = _KUNYA.search(name)
    if kunya:
        record["kunya"] = f"{kunya.group(1)} {kunya.group(2)}"
    year = _death_year(body)
    if year:
        record["death_year"] = year
    if shuyukh:
        record["shuyukh"] = shuyukh
    if talamidh:
        record["talamidh"] = talamidh
    if verdicts:
        record["verdicts"] = verdicts
    appraisals = extract_appraisals(body)
    if appraisals:
        record["appraisals"] = appraisals
    return record


def iter_sair(data: dict) -> Iterator[dict]:
    """Yield a graded record for every «N - Name» tarjama in سير أعلام النبلاء (book 10906)."""
    for num, name, body in _segment(data):
        rec = parse_entry(num, strip_diacritics(body), heading_name=name)
        if rec:
            yield rec


def parse_sair_file(path: str | Path) -> list[dict]:
    """Parse a downloaded ``{raw_dir}/books/10906.json`` (سير أعلام النبلاء) into graded narrator records."""
    return list(iter_sair(json.loads(Path(path).read_text(encoding="utf-8"))))
