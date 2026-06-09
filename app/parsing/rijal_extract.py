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

# تقريب abbreviates death years by DROPPING the hundreds: «من العاشرة مات سنة ست وثلاثين» means 236,
# not 36 — the century is recovered from the طبقة (Ibn Ḥajar's 12 generations, each ~a generation
# apart). _TAB_CENTER is the median death year of each طبقة; for a spelled year <100 we pick the
# century that lands the death closest to that median (Companions/early طبقات keep their genuine
# small years, since their median is itself <100).
_ORD_NUM = {"الاولي": 1, "الثانيه": 2, "الثالثه": 3, "الرابعه": 4, "الخامسه": 5, "السادسه": 6,
            "السابعه": 7, "الثامنه": 8, "التاسعه": 9, "العاشره": 10}
_TAB_CENTER = {1: 55, 2: 100, 3: 115, 4: 125, 5: 138, 6: 148,
               7: 165, 8: 190, 9: 210, 10: 235, 11: 258, 12: 280}


def _tabaqa_number(body: str) -> int | None:
    """The طبقة ordinal (1–12) of the entry, or None — from «من [كبار] العاشرة …»."""
    m = _TABAQA.search(body)
    if not m:
        return None
    span = normalize_for_search(body[m.start():m.end()])
    if "عشره" in span:                       # الحادية / الثانية عشرة → 11 / 12
        return 11 if "الحاديه" in span else (12 if "الثانيه" in span else None)
    for word, n in _ORD_NUM.items():
        if word in span:
            return n
    return None


def _century_from_tabaqa(year: int, tabaqa: int | None) -> int:
    """Recover a hundreds-dropped death year from the طبقة (تقريب abbreviates «ومائتين»)."""
    center = _TAB_CENTER.get(tabaqa or 0)
    if center is None:
        return year
    return min((year + 100 * k for k in range(4)), key=lambda y: abs(y - center))

# The leading operative term of a verdict (مراتب الجرح والتعديل), as whole words.
# An optional «ال» lets al-Dhahabī's «الحافظ»/«الإمام»/«الثقة» count as the verdict.
# «[إا]مام» / «[أا]علام»: al-Dhahabī grades his top men «الإمام» / «أحد الأعلام», but the al-Kashif
# source is hamza-inconsistent (writes «الامام» bare), so a hamza-exact «إمام» missed مالك/الأعمش →
# «غير معروف». Hamza-tolerant alternatives recover them (the index matcher already folds hamza).
_PRIMARY = re.compile(
    r"(?<!\w)(?:ال)?(كذاب|وضاع|متهم|متروك|ساقط|هالك|ضعيف|واهٍ|واه|منكر|مجهول|مستور|لين|"
    r"مقبول|صدوق|ثقة|ثبت|حافظ|حجة|[إا]مام|[أا]علام|متقن|عدل|صحابي)(?!\w)"
)
# Companions: often no طبقة and sometimes no one-word رتبة. تقريب grades the famous ones by
# DESCRIPTION, not the word «صحابي» — ابن عباس is «ابن عم رسول الله ﷺ ولد قبل الهجرة …» with no
# «صحابي» and no طبقة, so without these triggers a major Companion is mis-graded «غير معروف» (→ a
# chain through him reads «راوٍ مجهول»). All phrases below entail صحبة; none fits a later تابعي
# (who always carries a طبقة anyway, so this check is only reached for the un-graded, no-طبقة men).
_COMPANION = re.compile(
    r"(?<!\w)(?:صحابي|صحابية|صحابيٌّ|صحبة|له رؤية|رأى النبي|رأى رسول الله|"
    r"بدري|شهد بدرًا|شهد بدرا|شهد أحدًا|شهد أحدا|شهد الخندق|شهد الحديبية|شهد المشاهد|"
    r"شهد بيعة الرضوان|بايع تحت الشجرة|شهد فتح مكة|شهد فتح|"
    r"من السابقين|من المهاجرين|من الأنصار|من أهل بدر|"
    r"وفد على النبي|وفد على رسول الله|له وفادة|"
    r"ابن عم رسول الله|ابن عم النبي|ابن عمة رسول الله|"
    r"صحب النبي|صحب رسول الله|صحبه النبي|"
    r"خادم رسول الله|خادم النبي|خدم النبي|خدم رسول الله|"
    r"ولد قبل الهجرة|ولد على عهد النبي|ولد على عهد رسول الله|"
    r"من الصحابة|من أصحاب النبي|من أصحاب رسول الله|أحد الصحابة)(?!\w)"
)
# Narrative verdicts that replace a one-word رتبة. Includes al-Dhahabi's terse forms
# in الكاشف («وثق», «ضعف», «لا بأس», «صويلح»). Checked in order; first hit wins.
_FALLBACK: list[tuple[str, list[str]]] = [
    # «رماه»/«نسبه» alone are benign («نسبه إلى تلقين المشايخ», «رماه بالإرجاء/بالقدر») — require
    # the accusation itself («إلى الكذب/بالكذب/بالوضع»). «الكذب» already catches «إلى/بالكذب».
    ("كذاب", ["كذبه", "كذبوه", "يضع الحديث", "وضاع", "متهم بالكذب", "دجال", "الكذب", "بالوضع", "إلى الوضع"]),
    ("متروك", ["تركوه", "تركه", "ذاهب الحديث", "ليس بشيء"]),
    ("ضعيف", ["ضعفه", "ضعفوه", "ضعّف", "ضعف", "لا يحتج به", "منكر الحديث", "فيه ضعف", "واه",
              "خلط", "اختلط", "تغير", "سيئ الحفظ"]),
    ("صدوق", ["لا بأس", "ليس به بأس", "بحديثه بأس", "صالح الحديث", "صويلح", "محله الصدق"]),
    ("ثقة", ["وثقه", "وثقوه", "وثق", "ثقات"]),
]
# An accusation of lying made out of ENMITY/envy is a rejected جرح, not a verdict: «المهلب بن أبي
# صفرة … من ثقات الأمراء … فكان أعداؤه يرمونه بالكذب» is ثقة, not كذاب. A كذاب grade resting ONLY on
# an «accused-of» needle (الكذب/بالوضع) is dropped when an enmity marker is present (a critic's own
# «كذبه»/«وضاع» still stands).
_ENEMY_REJECTION = re.compile(r"أعداؤه|أعداءه|الأعداء|عدوه|عداوة|حسده|حساده|حاسد|لعداوة|للعداوة|حسدًا|حسدا|بغضًا|بغضا")
_ACCUSATION_NEEDLES = {"الكذب", "بالوضع", "إلى الوضع", "متهم بالكذب"}
# Where a name ends and the biography begins — cut the name at the first of these.
# «عن»/«سمع» start the teachers list (الكاشف: «name سمع … وعنه …»); a death/event/relation
# word begins the biography. A broad set (incl. feminine/inflected forms: ماتت، توفيت، كانت،
# وقيل، and events: أسلم، ولد، تزوّج، ولي، ذكره، والدة…) keeps the name from swallowing the
# whole tarjama — e.g. «… أم سلمة أم المؤمنين [تزوجها النبي …]» or «عمر … العدوي [يقال له …]».
_NAME_CUT = re.compile(
    r"\s(?:عن|عنه|وعنه|سمع|سمعت|مات|ماتت|توفي|توفى|توفيت|من|قال|قالت|قيل|وقيل|يقال|ويقال|روى|يروي|"
    r"وكان|كان|كانت|وكانت|نزيل|نزل|سكن|وفد|أصله|وثقه|ضعفه|تركه|كذبه|وقال|له|وله|ولها|لها|رمي|اختلط|"
    r"صنف|مشهور|تابعي|مخضرم|صحابي|صحابية|صحبة|شهد|ولد|ولدت|قتل|قتلت|استشهد|عاش|عاشت|تزوج|"
    r"تزوجت|تزوجها|ولي|وليت|بايع|أدرك|صحب|صحبت|ذكره|ذكرها|والد|والدة|مولى|ولأبيه|خليفة)\s"
)
# ضبط fragments (orthography notes) stripped from the name.
# ضبط fragments (orthography notes) interleaved INSIDE the name and stripped from it — تقريب
# writes «… البابلتي بموحدتين ولام مضمومة ومثناة ثقيلة أبو سعيد الحراني …», where the run between
# «البابلتي» and «أبو سعيد» is pure ضبط. Three classes, all whole-word: vowel/weight markers (with
# their بـ/و/ال forms), letter-class names (موحّدة/مثنّاة …), and letter NAMES — but the bare letter
# names (نون/لام/كاف …) double as nothing here yet ARE risky, so they are stripped ONLY when prefixed
# بـ/و/ال («ولام»، «بكاف»), which is unambiguously ضبط and never a real name token.
_DABT_FIXED = ("بفتح بضم بكسر بسكون بالفتح بالضم بالكسر بالتشديد بالتخفيف وفتح وضم وكسر وسكون "
               "وتشديد وتخفيف مصغر مكبر مصغرا مكبرا بعدها بعده أوله اوله آخره اخره").split()
_DABT_ADJ = ("مفتوحة مضمومة مكسورة ساكنة مشددة مخففة ثقيلة خفيفة مهملة معجمة موحدة موحّدة "
             "موحدتين مثناة مثلثة تحتانية فوقانية").split()
_DABT_LETTERS = ("ألف الف باء تاء ثاء جيم حاء خاء دال ذال راء زاي سين شين صاد ضاد طاء ظاء عين "
                 "غين فاء قاف كاف لام ميم نون هاء همزة").split()
_DABT = set(_DABT_FIXED)
for _w in _DABT_ADJ:
    _DABT |= {_w, "و" + _w, "ب" + _w, "ال" + _w}
for _l in _DABT_LETTERS:
    _DABT |= {"و" + _l, "ب" + _l, "ال" + _l, "وال" + _l, "بال" + _l}   # prefixed letter names only
_NOISE = re.compile(r"(?<!\w)(?:" + "|".join(sorted(_DABT, key=len, reverse=True)) + r")(?!\w)")
_KUNYA = re.compile(r"(?<!\w)(أبو|أبا|أبي|أم)\s+(\S+)")
# Words that, right before «أبو/أبي/أم …», make it a RELATIVE's kunya, not the subject's:
# a father in the nasab («محمد بن أبي بكر») or a kin reference («… ابن خالة أبي ذر»).
_KUNYA_NOT_SUBJECT = {normalize_for_search(w) for w in (
    "بن", "ابن", "خالة", "خال", "عمة", "عم", "جدة", "جد", "بنت", "ابنة", "أخت", "أخو", "أخي",
    "زوجة", "زوج", "مولى", "مولاة", "حليف", "امرأة", "صاحب", "ختن", "صهر", "نسيب", "والد", "والدة",
)}


def _own_kunya(name: str) -> "re.Match | None":
    """The subject's *own* kunya — skip an «أبو/أبي/أم X» that belongs to a relative: a father
    in the nasab («محمد بن أبي بكر») or a kin reference («خالد بن وهبان ابن خالة أبي ذر»)."""
    for m in _KUNYA.finditer(name):
        before = normalize_for_search(name[: m.start()]).split()
        if before and before[-1] in _KUNYA_NOT_SUBJECT:
            continue
        return m
    return None
_WS = re.compile(r"\s+")
# Folded tokens that identify no one on their own — a name made only of these («عبد الله»)
# is a truncation artifact, not a usable tarjama.
_GENERIC_NAME = {normalize_for_search(w) for w in ("عبد", "عبيد", "الله")}
# The gravest verdicts (كذّاب/وضّاع). A *bare* ism+father carrying one — no nisba, kunya, or
# death year — is almost always a truncated mis-parse that would contain-match and condemn every
# fuller namesake cited in a chain («يونس بن محمد» ↦ كذاب, though the real one is the ثقة المؤدّب).
_GRAVE = {normalize_for_search(w) for w in ("كذاب", "وضاع", "دجال", "يضع")}

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
    seg = body[m.start(): m.start() + 50]
    # The death YEAR follows «سنة» («مات سنة ٢٥٠» / «سنة سبع عشرة»); an AGE precedes it («مات وله
    # ٨٧ سنة», «ابن نيف وسبعين سنة») — never read the age as a year. So anchor on a «سنة» that is
    # FOLLOWED by a number (digit or spelled year-word), skipping an age «سنة» (preceded by one).
    for sm in re.finditer(r"\bسنة\b", seg):
        rest = seg[sm.end():].lstrip()
        digits = re.match(r"([\d٠-٩۰-۹]{2,3})\b", rest)
        if digits:                                   # «مات سنة ٢٥٠» (al-Kashif digit year)
            year = arabic_digits_to_int(digits.group(0))
            if year and 10 <= year <= 400:
                return year
        take: list[str] = []                          # «مات سنة سبع عشرة ومائة» (Taqrib spelled year)
        for tok in rest.split():
            t = tok.lstrip("و")
            if t in _UNITS or t in _TENS or t in _HUND or any(h in t for h in ("مائت", "مئت", "مائة", "مئة")):
                take.append(tok)
            elif take:
                break
            elif t in ("بضع", "نيف", "نحو"):
                continue                              # «سنة بضع وأربعين» — a lead-in, keep scanning
            else:
                break                                 # not a year-word after «سنة» → an age clause; try next «سنة»
        year = _parse_year(take)
        if year:
            return year
    # No «سنة» (al-Kashif's bare «توفي ١٧١», or «مات في رمضان ١٧١»): the first 2–3 digit run that
    # is NOT an age — reject a run right after an age word («مات وهو ابن ٨٧ سنة»).
    for dm in re.finditer(r"[\d٠-٩۰-۹]{2,3}", body[m.end():]):
        prev = body[m.end(): m.end() + dm.start()].split()
        if prev and prev[-1].lstrip("و") in ("ابن", "له", "عن", "بلغ", "عاش", "نحو", "نيف", "بضع"):
            continue
        year = arabic_digits_to_int(dm.group(0))
        if year and 10 <= year <= 400:
            return year
        break
    return None


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
        generic = {normalize_for_search(t) for t in alias.split()} - {"بن", "ابن", ""} <= _GENERIC_NAME
        if name_like and not generic and 3 <= len(alias) <= 40 and not any(c.isdigit() for c in alias):
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
    # a Companion has NO طبقة — so the (broad) Companion signal is trusted only when none is present,
    # which keeps «شهد بدرًا»/«صحبة» in a later man's tarjama from mis-grading him صحابي.
    if not has_tabaqa and _COMPANION.search(body):
        return "صحابي", len(before)
    ms = list(_PRIMARY.finditer(body))
    if ms:
        words = body[ms[-1].start():].split()[:6]
        return " ".join(words), len(before)
    for canonical, needles in _FALLBACK:
        hits = [n for n in needles if n in body]
        if not hits:
            continue
        # a كذاب resting ONLY on an «accused-of» needle is a rejected جرح when made out of enmity
        if canonical == "كذاب" and all(h in _ACCUSATION_NEEDLES for h in hits) and _ENEMY_REJECTION.search(body):
            continue
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
    # Drop malformed extractions: a name truncated at «… بن/ابن» (the nasab was cut off), or
    # one that reduces to a non-identifying generic («عبد الله»/«عبيد الله»). Either would
    # coincidentally contain-match every «عبد الله بن فلان» in a chain and mislabel real men.
    name_toks = name.split()
    if name_toks[-1] in ("بن", "ابن"):
        return None
    if {normalize_for_search(t) for t in name_toks} - {"بن", "ابن", ""} <= _GENERIC_NAME:
        return None
    folded = [t for t in (normalize_for_search(x) for x in name_toks) if t and t not in ("بن", "ابن")]
    # A name reduced to one identifying token («خالد») is a truncation, not a tarjama: as a bare
    # ism it exact-matches — and mis-grades — every «خالد …» downstream (here «خالد» ↦ صحابي).
    if len(folded) < 2:
        return None
    year = _death_year(body)
    # تقريب drops the hundreds from the year («من العاشرة مات سنة ست وثلاثين» = 236, not 36):
    # recover the century from the طبقة so the death year is usable for dedup / طبقة ordering.
    if year is not None and year < 100:
        year = _century_from_tabaqa(year, _tabaqa_number(body))
    # A bare ism+father (no nisba/kunya/death) given the gravest verdict is a mis-parse: «يونس بن
    # محمد» (really the ثقة المؤدّب), «عبد الرحمن بن محمد» (vs the صدوق المحاربي beside it). Kept, it
    # contain-matches and condemns every fuller namesake a chain cites.
    if (year is None and not _KUNYA.search(name) and len(folded) <= 3
            and not any(t.startswith("ال") and t.endswith("ي") and len(t) >= 4 for t in folded)
            and any(g in normalize_for_search(grade or "") for g in _GRAVE)):
        return None

    record: dict = {"name": name, "grade": grade or "غير محدد"}
    record["source"] = f"{source} (رقم {number})" if number is not None else source
    kunya = _own_kunya(name)   # the narrator's own kunya, not a relative's
    if kunya:
        record["kunya"] = f"{kunya.group(1)} {kunya.group(2)}"
    aliases = _aliases(body)      # laqab/shuhra the man is also known by
    if aliases:
        record["aliases"] = aliases
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
