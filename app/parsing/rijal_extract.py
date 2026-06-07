"""Extract narrator (رجال) entries from a *تقريب التهذيب*-style biographical book.

تقريب التهذيب (Ibn Ḥajar) is the ideal source for grading isnads: one terse,
numbered entry per narrator covering the men of the Six Books, each ending with the
critic's verdict (ثقة / صدوق / مقبول / مستور / مجهول / ضعيف / متروك …), his طبقة, his
death, and the rumūz of who narrated from him. الكاشف (al-Dhahabī) follows the same
terse style. This turns each numbered entry into a record::

    {"name", "kunya", "grade", "death_year", "source"}

``grade`` is the verdict phrase; :func:`app.rijal.grades.classify` maps it to a
category/rank. Verbose biographies (تهذيب الكمال, الجرح والتعديل) are out of scope —
their prose doesn't reduce cleanly to one verdict — but the terse books already cover
essentially every narrator of the Six Books, which is what an isnad check needs.

The verdict in تقريب sits immediately before «من [the Nth generation]», so we anchor
on the طبقة and read the operative term just before it; Companions (who have no طبقة)
are recognised from صحابي / شهد بدرًا / من السابقين and graded صحابي (عدول بالإجماع).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, Iterator

from app.parsing.html_clean import arabic_digits_to_int, clean_block
from app.parsing.normalize import normalize_for_search

# Entry boundary: a line starting with «NUM- » (a real tarjama) or «[] » (a cross-
# reference / تمييز line we skip). Numbers are Arabic-Indic in the source.
_BOUNDARY = re.compile(r"(?:^|\n)[ \t]*(?:([\d٠-٩۰-۹]+)[ \t]*-\s|\[\]\s)")

# طبقة anchor — the verdict sits immediately before «من [the Nth generation]».
_ORD = ("الأولى|الثانية|الثالثة|الرابعة|الخامسة|السادسة|السابعة|الثامنة|التاسعة|"
        "العاشرة|الحادية\\s+عشرة|الثانية\\s+عشرة")
_TABAQA = re.compile(rf"\bمن\s+(?:كبار\s+|صغار\s+|أواسط\s+|صغرى\s+|الوسطى\s+)?(?:{_ORD})\b")

# The leading operative term of a verdict (مراتب الجرح والتعديل), as whole words.
# An optional «ال» lets al-Dhahabī's «الحافظ»/«الإمام»/«الثقة» count as the verdict.
_PRIMARY = re.compile(
    r"(?<!\w)(?:ال)?(كذاب|وضاع|متهم|متروك|ساقط|هالك|ضعيف|واهٍ|واه|منكر|مجهول|مستور|لين|"
    r"مقبول|صدوق|ثقة|ثبت|حافظ|حجة|إمام|متقن|عدل|صحابي)(?!\w)"
)
# Companions: often no طبقة and sometimes no one-word رتبة.
_COMPANION = re.compile(
    r"(?<!\w)(صحابي|صحابية|له صحبة|شهد بدرًا|شهد بدرا|بدري|من السابقين|"
    r"بايع تحت الشجرة|من أهل بدر|من المهاجرين الأولين)(?!\w)"
)
# Narrative verdicts that replace a one-word رتبة. Includes al-Dhahabi's terse forms
# in الكاشف («وثق», «ضعف», «لا بأس», «صويلح»). Checked in order; first hit wins.
_FALLBACK: list[tuple[str, list[str]]] = [
    ("كذاب", ["كذبه", "كذبوه", "يضع الحديث", "متهم بالكذب", "دجال", "الكذب", "رماه", "نسبه"]),
    ("متروك", ["تركوه", "تركه", "ذاهب الحديث", "ليس بشيء"]),
    ("ضعيف", ["ضعفه", "ضعفوه", "ضعّف", "ضعف", "لا يحتج به", "منكر الحديث", "فيه ضعف", "واه",
              "خلط", "اختلط", "تغير", "سيئ الحفظ"]),
    ("صدوق", ["لا بأس", "ليس به بأس", "بحديثه بأس", "صالح الحديث", "صويلح", "محله الصدق"]),
    ("ثقة", ["وثقه", "وثقوه", "وثق", "ثقات"]),
]
# Where a name ends and the biography begins — cut the name at the first of these.
# «عن»/«سمع» start the teachers list (الكاشف: «name سمع … وعنه …»); «مات/توفي» the death.
_NAME_CUT = re.compile(
    r"\s(?:عن|عنه|وعنه|سمع|سمعت|مات|توفي|توفى|من|قال|قيل|روى|يروي|وكان|كان|نزيل|نزل|سكن|"
    r"وفد|أصله|وثقه|ضعفه|تركه|كذبه|وقال|له|رمي|اختلط|صنف|مشهور|تابعي|مخضرم|صحابي|صحابية|شهد)\s"
)
# ضبط fragments (orthography notes) stripped from the name.
_NOISE = re.compile(
    r"(?<!\w)(?:بفتح|بضم|بكسر|بسكون|بالفتح|بالضم|بالكسر|بالتشديد|بالتخفيف|مصغر|مكبر|"
    r"المهملة|المعجمة|الموحدة|المثناة|المثلثة|التحتانية|الفوقانية|الساكنة|"
    r"وسكون|وفتح|وكسر|وضم|وتشديد|وتخفيف|ثقيلة|خفيفة)(?!\w)"
)
_KUNYA = re.compile(r"(?<!\w)(أبو|أبا|أبي|أم)\s+(\S+)")
_WS = re.compile(r"\s+")

# Laqab / shuhra cues: «المعروف بـ…», «يقال له…», «لقبه…» introduce another name the man
# is known by — captured as an alias so a chain that cites him by it links to one person.
# Group A needs the particle بـ; group B (لقبه/يقال له) is followed by the laqab directly.
_ALIAS_CUE = re.compile(
    r"(?:(?:المعروف|المشهور|يعرف|يُعرف|الملقب|يلقب|يُلقب)\s+بـ?\s*"
    r"|(?:لقبه|يقال\s+له|ويقال\s+له)\s+)"
)
# Where the captured laqab ends — the first biography word / verb / verdict.
_ALIAS_STOP = {normalize_for_search(w) for w in (
    "عن عنه وعنه سمع سمعت روى يروي مات توفي توفى من قال قيل وكان كان نزيل نزل سكن وثقه "
    "ضعفه تركه كذبه له رمي اختلط صنف صاحب مشهور تابعي مخضرم صحابي صحابية شهد في على وفي "
    "ثقة صدوق ضعيف مقبول لين مستور مجهول متروك حافظ امام ثبت وهو وهي احد بفتح بضم بكسر "
    "بسكون ايضا"
).split()}


# OCR sometimes glues the verdict to the next word («صدوقتوفي», «ثقةمات»); split them.
_DEGLUE = re.compile(r"(صدوق|ثقة|ضعيف|مقبول|لين|مستور|صالح|حافظ|مجهول|متروك)(توفي|مات)")


def _debracket(text: str) -> str:
    """Drop the bracket characters but keep their content — editors often restore the
    رتبة or the kunya inside «[ ]» (e.g. «[مقبول]»), which we must not throw away."""
    return _DEGLUE.sub(r"\1 \2", text.replace("[", " ").replace("]", " "))

# Spelled Arabic numbers for death years.
_UNITS = {"إحدى": 1, "احدى": 1, "واحدة": 1, "واحد": 1, "اثنتين": 2, "اثنين": 2, "ثنتين": 2,
          "ثلاث": 3, "ثلاثة": 3, "أربع": 4, "اربع": 4, "أربعة": 4, "خمس": 5, "خمسة": 5,
          "ست": 6, "ستة": 6, "سبع": 7, "سبعة": 7, "ثمان": 8, "ثماني": 8, "ثمانية": 8,
          "تسع": 9, "تسعة": 9}
_TENS = {"عشر": 10, "عشرة": 10, "عشرين": 20, "ثلاثين": 30, "أربعين": 40, "اربعين": 40,
         "خمسين": 50, "ستين": 60, "سبعين": 70, "ثمانين": 80, "تسعين": 90}
_HUND = {"مائة": 100, "مئة": 100, "مائتين": 200, "مئتين": 200,
         "ثلاثمائة": 300, "أربعمائة": 400}


def _parse_year(words: list[str]) -> int | None:
    total, seen = 0, False
    for raw in words:
        t = raw.lstrip("و")
        if t in _UNITS:
            total += _UNITS[t]; seen = True
        elif t in _TENS:
            total += _TENS[t]; seen = True
        elif t in _HUND:
            total += _HUND[t]; seen = True
        elif any(h in t for h in ("مائت", "مئت")):
            total += 200; seen = True
        elif any(h in t for h in ("ثلاثمائة", "ثلاثمئة")):
            total += 300; seen = True
        elif any(h in t for h in ("مائة", "مئة")):
            total += 100; seen = True
    return total if seen and 10 <= total <= 360 else None


def _death_year(body: str) -> int | None:
    m = re.search(r"(?<!\w)(?:مات|توفي|توفى|توفّي)\b", body)
    if not m:
        return None
    seg = body[m.start(): m.start() + 45]
    # الكاشف writes the year in digits («توفي ١٧١»); take the first 2–3 digit run.
    digits = re.search(r"[\d٠-٩۰-۹]{2,3}", seg)
    if digits:
        year = arabic_digits_to_int(digits.group(0))
        if year and 10 <= year <= 400:
            return year
    # تقريب spells it out («مات سنة سبع عشرة»).
    spelled = re.search(r"سنة\s+(.+)", seg)
    if not spelled:
        return None
    take: list[str] = []
    for tok in spelled.group(1).split():
        t = tok.lstrip("و")
        if t in _UNITS or t in _TENS or t in _HUND or any(h in t for h in ("مائت", "مئت", "مائة", "مئة")):
            take.append(tok)
        elif take:
            break
        elif tok not in ("بضع", "نيف", "نحو"):
            break
    return _parse_year(take)


def _aliases(body: str) -> list[str]:
    """Other names the man is *known by* (laqab/shuhra), captured conservatively.

    Only clear cues count, the laqab is cut at the first biography word and capped at
    three tokens, and a bare single token is kept only when it is a nisba («الأعمش») —
    so we never invent a spurious alias (e.g. «المشهور بشر» yields nothing)."""
    out: list[str] = []
    for cue in _ALIAS_CUE.finditer(body):
        words: list[str] = []
        for raw in body[cue.end():].split():
            tok = raw.strip("،.؛:؟»«()[]\"'")
            folded = normalize_for_search(tok.lstrip("و"))
            if not folded or folded in _ALIAS_STOP:
                break
            words.append(tok)
            if len(words) >= 3:
                break
        alias = _WS.sub(" ", " ".join(words)).strip(" -،")
        name_like = len(alias.split()) >= 2 or (alias.startswith("ال") and len(alias) >= 4)
        if name_like and 3 <= len(alias) <= 40 and not any(c.isdigit() for c in alias):
            out.append(alias)
    return list(dict.fromkeys(out))   # de-duplicated, order preserved


def _trim_name(text: str) -> str:
    # the name ends at the first biography cue (عن/سمع/مات …) OR the first verdict word,
    # whichever comes first — al-Dhahabī puts the رتبة («ثقة») right before «سمع».
    padded = f" {text} "
    end = len(padded)
    cut = _NAME_CUT.search(padded)
    if cut:
        end = cut.start()
    verdict = _PRIMARY.search(padded)
    if verdict and verdict.start() < end:
        end = verdict.start()
    text = _NOISE.sub(" ", padded[:end])
    return _WS.sub(" ", text).strip(" -،")


def _extract_grade(body: str, before: str, has_tabaqa: bool) -> tuple[str, int]:
    """Return ``(grade_phrase, name_end_index_in_before)``."""
    if has_tabaqa:
        window_start = max(0, len(before) - 45)
        ms = list(_PRIMARY.finditer(before, window_start)) or list(_PRIMARY.finditer(before))
        if ms:
            return " ".join(before[ms[-1].start():].split()[:5]), ms[-1].start()
    if _COMPANION.search(body):
        return "صحابي", len(before)
    ms = list(_PRIMARY.finditer(body))
    if ms:
        words = body[ms[-1].start():].split()[:6]
        return " ".join(words), len(before)
    for canonical, needles in _FALLBACK:
        if any(n in body for n in needles):
            return canonical, len(before)
    return "", len(before)


def _entry_to_record(number: int | None, body: str, source: str) -> dict | None:
    body = _WS.sub(" ", _debracket(body)).strip()
    if len(body) < 4:
        return None

    anchor = _TABAQA.search(body)
    before = body[: anchor.start()] if anchor else body
    grade, name_end = _extract_grade(body, before, anchor is not None)

    name = _trim_name(before[:name_end])
    if len(name) < 3:
        return None

    record: dict = {"name": name, "grade": grade or "غير محدد"}
    record["source"] = f"{source} (رقم {number})" if number is not None else source
    kunya = _KUNYA.search(name)   # the narrator's own kunya, not a student's
    if kunya:
        record["kunya"] = f"{kunya.group(1)} {kunya.group(2)}"
    aliases = _aliases(body)      # laqab/shuhra the man is also known by
    if aliases:
        record["aliases"] = aliases
    year = _death_year(body)
    if year:
        record["death_year"] = year
    return record


def iter_narrators(
    pages: Iterable[dict], source: str = "تقريب التهذيب", start_page_id: int | None = None
) -> Iterator[dict]:
    """Yield narrator records for every numbered tarjama across the book's pages.

    ``start_page_id`` skips the editor's muqaddima (long in الكاشف), whose numbered
    lists would otherwise be mistaken for tarjamas — pass the page where entry 1 starts.
    """
    pages = [p for p in pages if start_page_id is None or p.get("pg", 0) >= start_page_id]
    full = "\n".join(
        clean_block(p.get("text") or "")
        for p in sorted(pages, key=lambda p: p.get("pg", 0))
    )
    bounds = list(_BOUNDARY.finditer(full))
    for i, match in enumerate(bounds):
        if match.group(1) is None:   # a «[]» cross-reference line — skip
            continue
        end = bounds[i + 1].start() if i + 1 < len(bounds) else len(full)
        record = _entry_to_record(
            arabic_digits_to_int(match.group(1)), full[match.end():end], source
        )
        if record:
            yield record


def _first_entry_page(data: dict) -> int | None:
    """Page id where the numbered tarjamas start, from the ``numbers`` index
    (entry number → page id) — used to skip the editor's muqaddima."""
    numbers = (data.get("indexes") or {}).get("numbers") or {}
    pages = [int(v) for v in numbers.values() if str(v).lstrip("-").isdigit()]
    return min(pages) if pages else None


def parse_rijal_file(path: str | Path, source: str | None = None) -> list[dict]:
    """Parse a downloaded ``{raw_dir}/books/{id}.json`` رجال book into narrator records."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    name = source or data.get("name") or "تقريب التهذيب"
    return list(iter_narrators(
        data.get("pages", []), source=name, start_page_id=_first_entry_page(data)
    ))
