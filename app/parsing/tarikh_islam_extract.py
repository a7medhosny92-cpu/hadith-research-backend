"""Extract narrator records from تاريخ الإسلام ووفيات المشاهير والأعلام (الذهبي, ت بشار عواد, 35100).

The COMPREHENSIVE late-narrator source: a طبقات-by-death-decade dictionary covering EVERY narrator up to
700 AH — exactly the post-Six-Books الأصم-class (al-Ḥākim/al-Bayhaqī's شيوخ) the رجال base lacks.

**Segmentation (heading-based, calibrated on the real book's `indexes.headings`).** Unlike سير, تاريخ
الإسلام has **no per-tarjama number** (`indexes.numbers` is empty) — its narrator tarjamas are the LEVEL-3
headings (≈30,864, the bulk; the famous Companions are LEVEL-2 «ترجمة فلان»), each a bare full NAME on its
page. The first ~340 pages are the محقق's STUDY of al-Dhahabī (skipped by page) and the early طبقات are
سيرة/مغازي EVENTS («غزوة بدر»، «سرية فلان» — skipped by an event stop-list, never narrators). A heading is
mapped to its body by PAGE (body runs to the next heading), like سير.

Body markers: شيوخ «سمع/روى عن/حدّث عن», تلاميذ «وعنه/روى عنه», death «توفي/مات … سنة …», critics «قال فلان: …»
+ al-Dhahabī's DIRECT «وكان ثقة». Grade = weakest cited جرح/تعديل, else «غير معروف» (coverage, no default ثقة).
"""

from __future__ import annotations

import bisect
import json
import re
from pathlib import Path
from typing import Iterator

from app.parsing.appraisals import extract_appraisals
from app.parsing.html_clean import clean_block
from app.parsing.jarh_extract import _KUNYA, _block_between, _names, _verdicts
from app.parsing.normalize import strip_diacritics
from app.parsing.rijal_extract import _death_year
from app.parsing.sair_extract import _FOOTNOTE, _NARRATIVE, _WS, _clean_name, _grade_from, _locate
from app.rijal.grades import classify

TARIKH_ISLAM_BOOK_ID = 35100
_SOURCE = "تاريخ الإسلام (الذهبي، ت بشار عواد، رقم 35100)"
_STUDY_END_PAGE = 343  # the محقق's study (مقدمة التحقيق) ends ~247; مقدمة المؤلف begins 343 — skip before it.

# شيوخ: «سمع X» (dominant) / «روى عن» / «حدّث عن»; تلاميذ: «وعنه» / «روى عنه» / «حدّث عنه».
_SHU = re.compile(r"(?:سمع|حدّ?ث\s+عن|رو[ىي]\s+عن)(?!ه)")
_TAL = re.compile(r"(?:وعنه|رو[ىي]\s+عنه|حدّ?ث\s+عنه)")
_NET_END = re.compile(
    r"سمعت|حدثنا|أخبرنا|أنبأنا|قال|سئل|مات|توفي|قاله|يقال|ذكره|قلت|وكان|كان|"
    r"ضعّفه|ضعفه|وثّقه|وثقه|آخرون|وجماعة|وخلق|وغيرهم|وطائفة"
)
# al-Dhahabī's DIRECT assessment «وكان ثقة» / «صدوقًا» / «ضعيفًا» — a verdict by construction (HADITH grades
# only, not «صالحًا» = piety), beyond the attributed «قال فلان: …» that `_verdicts` reads.
_DIRECT = re.compile(r"كان\s+(ثقة|ثبتا?|حافظا?|إماما?|صدوقا?|ضعيفا?|واهيا?|متروكا?|كذابا?|لينا?|مقبولا?|مجهولا?)")
# A heading that is NOT a narrator: the محقق's study sections, the طبقة/year headers, and the سيرة/مغازي
# EVENTS — every تاريخ الإسلام heading that opens with one of these is a topic, not a man.
_TARJAMA_PREFIX = re.compile(r"^(?:ترجمة|ذكر ترجمة)\s+")
_EVENT_HEAD = (
    "غزوة", "سرية", "بعث", "قصة", "ذكر", "فصل", "باب", "الباب", "الفصل", "مقدمة", "توطئة", "تمهيد",
    "مدخل", "السنة", "سنة", "الطبقة", "طبقة", "حوادث", "وفي", "وفيها", "فيها", "مصورات", "أمر", "نزول",
    "تزويج", "إسلام", "مقتل", "قتل", "فتح", "عمرة", "حديث", "خطبة", "أسماء", "عدد", "قسم", "بقية",
    "رؤيا", "شأن", "قدوم", "وصف", "تنظيم", "طبيعة", "عناصر", "نهج", "أنواع", "طرائق", "مظاهر", "أسس",
    "الخطة", "العلاقة", "أولا", "ثانيا", "ثالثا", "رابعا", "خامسا", "سادسا", "سابعا", "ثامنا", "تاسعا",
    "أ ", "ب ", "ج ", "د ", "هـ", "و ", "ز ", "شهداء", "استشهد", "وفاة", "موت", "هجرة", "خبر",
)


def _ti_name(title: str) -> str | None:
    """A heading title → a clean narrator name, or ``None`` if it is an event / section / study head."""
    name = _TARJAMA_PREFIX.sub("", _WS.sub(" ", title or "").strip(" .،:-—*"))
    name = _clean_name(name) or name           # stop at any leaked body marker
    if not name or name.startswith(_EVENT_HEAD) or len(name.split()) < 2:
        return None
    return name


def _tarjama_heads(data: dict) -> list[tuple[int, str]]:
    """Ordered ``(page, name)`` for every narrator tarjama: a LEVEL-3 heading (the bulk) or a LEVEL-2
    «ترجمة فلان», past the محقق's study (page ≥ 343), that is a NAME and not a سيرة/مغازي event."""
    out: list[tuple[int, str]] = []
    for h in (data.get("indexes") or {}).get("headings") or []:
        page, level = h.get("page"), h.get("level")
        if page is None or page < _STUDY_END_PAGE or level not in (2, 3):
            continue
        if level == 2 and not _TARJAMA_PREFIX.match(_WS.sub(" ", h.get("title") or "").strip()):
            continue                            # a level-2 head is a narrator only when it is «ترجمة فلان»
        name = _ti_name(h.get("title") or "")
        if name:
            out.append((int(page), name))
    return out


def _segment(data: dict) -> Iterator[tuple[str, str]]:
    """Walk the narrator headings and yield ``(name, body)`` — each mapped to its body by PAGE (the body
    runs from this heading's located position to the next heading's), exactly like سير."""
    heads = _tarjama_heads(data)
    if not heads:
        return
    pages = sorted(
        ((p["pg"], _FOOTNOTE.split(clean_block(p.get("text") or ""), 1)[0])
         for p in data.get("pages", []) if p.get("pg") is not None),
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
    for pg, name in heads:
        if pg in page_start:
            base, pend = page_start[pg], page_end[pg]
        else:
            i = bisect.bisect_right(pgs, pg) - 1
            if i < 0:
                starts.append(-1)
                continue
            base, pend = page_start[pgs[i]], page_end[pgs[i]]
        frm = max(base - 4, cursor.get(pg, base - 4))
        pos = _locate(stripped, name, max(0, frm), pend)
        if pos < 0:
            pos = max(0, frm)
        starts.append(pos)
        cursor[pg] = pos + 1

    n = len(heads)
    for i, (_pg, name) in enumerate(heads):
        s = starts[i]
        if s < 0:
            continue
        e = len(full)
        for j in range(i + 1, n):
            if starts[j] > s:
                e = starts[j]
                break
        yield name, full[s:e]


def parse_entry(body: str, name: str) -> dict | None:
    """One تاريخ الإسلام tarjama body + its heading name → a graded record, or ``None``. A real narrator
    must show a documented شيخ/تلميذ OR a cited verdict — a stray non-tarjama span is dropped, never graded."""
    body = _WS.sub(" ", body).strip()
    if not name or len(body) < 8:
        return None
    shuyukh = _names(_block_between(body, _SHU, _TAL, _NET_END))
    talamidh = _names(_block_between(body, _TAL, _NET_END))
    verdicts = [v for v in _verdicts(body) if not _NARRATIVE.search(v)]   # drop reported-speech «scenes»
    verdicts += ["كان " + m.group(1) for m in _DIRECT.finditer(body)]     # al-Dhahabī's direct «وكان ثقة»
    if not (shuyukh or talamidh or verdicts):
        return None
    record: dict = {"name": name, "grade": _grade_from(verdicts), "source": _SOURCE}
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


def iter_tarikh_islam(data: dict) -> Iterator[dict]:
    """Yield a graded record for every narrator tarjama in تاريخ الإسلام (book 35100)."""
    for name, body in _segment(data):
        rec = parse_entry(strip_diacritics(body), name)
        if rec:
            yield rec


def parse_tarikh_islam_file(path: str | Path) -> list[dict]:
    """Parse a downloaded ``{raw_dir}/books/35100.json`` (تاريخ الإسلام) into graded narrator records."""
    return list(iter_tarikh_islam(json.loads(Path(path).read_text(encoding="utf-8"))))
