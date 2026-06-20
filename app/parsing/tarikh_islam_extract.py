"""Extract narrator records from تاريخ الإسلام ووفيات المشاهير والأعلام (الذهبي, ت بشار عواد, 35100).

The COMPREHENSIVE late-narrator source: a طبقات-by-death-decade dictionary covering EVERY narrator up to
700 AH — exactly the post-Six-Books الأصم-class (al-Ḥākim/al-Bayhaqī's شيوخ) the رجال base lacks. Same
HEADING-based structure as سير (`indexes.headings` carry «N - full name», numbers restart each طبقة so the
PAGE locates the body), so the سير segmentation is reused verbatim; only the network markers differ and a
MUQADDIMA gate is added (the محقق's ~150-page study of al-Dhahabī opens the book with «N - مشهد عروة» /
«N - ابنته أمة العزيز» topic/relative entries that are NOT narrators).

Body markers (verified on the real الأصم-class tarjamas): شيوخ by «سمع …» / «روى عن …» / «حدّث عن …»,
تلاميذ by «وعنه …» / «روى عنه …», death «توفي/مات … سنة …», critics «قال فلان: …». Grade = weakest cited
جرح/تعديل verdict, else «غير معروف» (coverage pattern — no inclusion توثيق, so no default «ثقة»).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator

from app.parsing.appraisals import extract_appraisals
from app.parsing.jarh_extract import _KUNYA, _block_between, _names, _verdicts
from app.parsing.normalize import strip_diacritics
from app.parsing.rijal_extract import _death_year
from app.parsing.sair_extract import _NARRATIVE, _WS, _clean_name, _grade_from, _segment
from app.rijal.grades import classify

TARIKH_ISLAM_BOOK_ID = 35100
_SOURCE = "تاريخ الإسلام (الذهبي، ت بشار عواد، رقم 35100)"

# شيوخ: «سمع X» (the dominant form in تاريخ الإسلام) / «روى عن» / «حدّث عن» — NOT «…عنه» (a تلميذ).
_SHU = re.compile(r"(?:سمع|حدّ?ث\s+عن|رو[ىي]\s+عن)(?!ه)")
# تلاميذ: «وعنه …» (the dominant terse form) / «روى عنه» / «حدّث عنه».
_TAL = re.compile(r"(?:وعنه|رو[ىي]\s+عنه|حدّ?ث\s+عنه)")
# A network block ends at a transmission/speech verb, death, verdict verb, or a list-terminator.
_NET_END = re.compile(
    r"سمعت|حدثنا|أخبرنا|أنبأنا|قال|سئل|مات|توفي|قاله|يقال|ذكره|قلت|وكان|كان|"
    r"ضعّفه|ضعفه|وثّقه|وثقه|آخرون|وجماعة|وخلق|وغيرهم|وطائفة"
)
# al-Dhahabī's DIRECT assessment «وكان ثقة» / «وكان صدوقًا» / «وكان ضعيفًا» — a verdict by construction
# (NOT the attributed «قال فلان: …» that `_verdicts` reads). HADITH grades only (not «صالحًا» = piety).
_DIRECT = re.compile(r"كان\s+(ثقة|ثبتا?|حافظا?|إماما?|صدوقا?|ضعيفا?|واهيا?|متروكا?|كذابا?|لينا?|مقبولا?|مجهولا?)")
# MUQADDIMA / non-narrator heads: the محقق's study opens with al-Dhahabī's teaching posts and family, and
# the طبقات carry section/topic heads — none is a narrator. A real tarjama still needs network OR a verdict
# (a topic like «مشهد عروة» has neither), so this list is a fast pre-filter, the network/verdict gate the proof.
_JUNK_HEAD = (
    "باب", "كتاب", "فصل", "ذكر", "مقدمة", "فأما", "وأما", "أخوه", "وابنه", "ابنه", "ابنته", "بنته",
    "مشهد", "دار", "تربة", "مدرسة", "خزانة", "زاوية", "رباط", "جامع", "مسجد", "حوادث", "الطبقة", "وفيات",
    "ومن", "وفيها", "فيها", "ثم", "أهل",
)


def parse_entry(number: int | None, body: str, heading_name: str | None = None) -> dict | None:
    """One تاريخ الإسلام tarjama → a graded record, or ``None`` for the muqaddima / a non-narrator entry.

    The name is the (clean) heading; a real narrator must show a documented شيخ/تلميذ OR a cited verdict —
    so a محقق-intro topic «مشهد عروة» (no network, no جرح) is dropped, never graded."""
    body = _WS.sub(" ", body).strip()
    if len(body) < 8:
        return None
    name = heading_name or _clean_name(body)
    if not name or name.startswith(_JUNK_HEAD) or len(name.split()) < 2:
        return None
    shuyukh = _names(_block_between(body, _SHU, _TAL, _NET_END))
    talamidh = _names(_block_between(body, _TAL, _NET_END))
    verdicts = [v for v in _verdicts(body) if not _NARRATIVE.search(v)]   # drop reported-speech «scenes»
    verdicts += ["كان " + m.group(1) for m in _DIRECT.finditer(body)]     # al-Dhahabī's direct «وكان ثقة»
    if not (shuyukh or talamidh or verdicts):
        return None                       # no documented network and no جرح → a topic/relative, not a narrator
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


def iter_tarikh_islam(data: dict) -> Iterator[dict]:
    """Yield a graded record for every narrator tarjama in تاريخ الإسلام (book 35100)."""
    for num, name, body in _segment(data):
        rec = parse_entry(num, strip_diacritics(body), heading_name=name)
        if rec:
            yield rec


def parse_tarikh_islam_file(path: str | Path) -> list[dict]:
    """Parse a downloaded ``{raw_dir}/books/35100.json`` (تاريخ الإسلام) into graded narrator records."""
    return list(iter_tarikh_islam(json.loads(Path(path).read_text(encoding="utf-8"))))
