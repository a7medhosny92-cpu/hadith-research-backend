"""Classify a narrator's verdict (جرح وتعديل) into a category and a reliability rank.

Hadith critics grade each narrator with a terse formula whose *leading* term is the
operative judgement — "ثقة حافظ", "صدوق يهم", "ضعيف رافضي", "متروك". We map that to a
category and an integer rank (higher = more reliable) so a chain can be assessed by
its weakest link. The ladder follows the well-known مراتب الجرح والتعديل.

This is a deliberately conservative reading: when a صدوق verdict carries a weakening
qualifier (يهم/اختلط/خلط…), the narrator is nudged down a notch.
"""

from __future__ import annotations

import re

from app.parsing.normalize import NEGATORS, normalize_for_search

# Positive ranks that a preceding negator («غير عدل») cancels.
_POSITIVE = {"ثقة", "صدوق", "مقبول", "صحابي"}

#: category → rank (10 best … 0 worst)
RANKS: dict[str, int] = {
    "صحابي": 10,
    "ثقة": 9,
    "صدوق": 7,
    "صدوق له أوهام": 6,
    "مقبول": 5,
    "لين": 4,
    "مجهول": 3,
    "ضعيف": 2,
    "متروك": 1,
    "كذاب": 0,
}

# category → trigger phrases. We pick the category whose phrase occurs *earliest*
# in the verdict (so the leading term wins). Phrases are folded at import.
_RULES: list[tuple[str, list[str]]] = [
    ("كذاب", ["كذاب", "وضاع", "يضع الحديث", "متهم بالكذب", "متهم بالوضع", "دجال", "يكذب"]),
    ("متروك", ["متروك", "ساقط", "ذاهب الحديث", "هالك", "ليس بشيء", "تركوه", "متهم"]),
    ("ضعيف", ["ضعيف", "واه", "منكر الحديث", "ليس بثقة", "فيه ضعف", "لا يحتج به", "ضعفوه"]),
    ("لين", ["لين الحديث", "لين", "فيه لين", "يعتبر به", "ليس بالقوي", "ليس بذاك القوي", "ليس بذاك"]),
    ("مجهول", ["مجهول", "مستور", "لا يعرف", "لا يعرف حاله"]),
    ("مقبول", ["مقبول"]),
    ("صدوق", ["صدوق", "لا بأس به", "ليس به بأس", "صالح الحديث", "محله الصدق"]),
    ("ثقة", ["ثقة", "ثبت", "حافظ", "حجة", "امام", "متقن", "عدل", "جبل"]),
    # صحابي is often given by DESCRIPTION, not the word «صحابي» — عبد الرحمن بن عوف is «أحد العشرة
    # أسلم قديمًا …» (no «صحابي», no طبقة) and was mis-graded «غير معروف» → a chain through a major
    # Companion read «راوٍ مجهول». These phrases all entail صحبة (mirrors rijal_extract._SAHABI_DESC).
    ("صحابي", ["صحابي", "صحابية", "صحبة", "له صحبة", "أحد العشرة", "من العشرة", "العشرة المبشرة",
               "أسلم قديما", "من السابقين", "بدري", "شهد بدرا", "شهد أحدا", "شهد الحديبية",
               "رأى النبي", "رأى رسول الله", "له رؤية", "بايع تحت الشجرة", "من أهل بدر",
               "من أصحاب النبي", "من أصحاب رسول الله", "أحد الصحابة",
               "مذكور في الصحابة", "ذكر في الصحابة", "ذكره في الصحابة", "له إدراك"]),
]
_QUALIFIERS = ["يهم", "يخطئ", "اوهام", "اختلط", "خلط", "تغير", "سيئ الحفظ", "له مناكير", "ربما وهم"]

_RULES_N = [(cat, [normalize_for_search(p) for p in phrases]) for cat, phrases in _RULES]
_QUALIFIERS_N = [normalize_for_search(q) for q in _QUALIFIERS]

# A FALSE PROPHET's epithet — «مسيلمةُ الكذّاب»، «الأسودُ [العنسيُّ] الكذّاب»، «طليحةُ/سجاحُ الكذّاب» — is a
# STORY character, never a جرح of the narrator. A matn «جاء مسيلمةُ الكذّاب إلى رسول الله ﷺ …» that leaked
# into a verdict field must NOT grade the narrator (أبو عامر العقديّ، ثقة) «كذّاب» and sink a صحيح البخاري
# chain. Neutralise the epithet before classifying (folded forms: ة→ه, shadda dropped).
_FALSE_PROPHET_KADHAB = re.compile(r"(?:مسيلمه|الاسود|طليحه|سجاح)\s+(?:العنسي\s+)?الكذاب")


def _first_index(haystack: str, needle: str) -> int:
    pos = haystack.find(f" {needle} ")
    if pos < 0:                              # also accept the definite-article form
        pos = haystack.find(f" ال{needle} ")  # «الحافظ»/«الإمام»/«الثقة» (al-Dhahabī)
    return pos if pos >= 0 else 10**9


def classify(verdict: str) -> tuple[str, int | None]:
    """Return ``(category, rank)`` for a raw verdict; ``("غير معروف", None)`` if unread."""
    text = f" {normalize_for_search(verdict)} "
    text = _FALSE_PROPHET_KADHAB.sub(" مسيلمه ", text)   # drop the false-prophet «الكذّاب» epithet
    best_cat: str | None = None
    best_pos = 10**9
    for cat, phrases in _RULES_N:
        pos = min(_first_index(text, p) for p in phrases)
        if pos < best_pos:
            best_cat, best_pos = cat, pos
    if best_cat is None:
        return "غير معروف", None
    # a negator just before a positive verdict cancels it: «غير عدل» / «ليس بعدلٍ» is not توثيق
    window = text[max(0, best_pos - 12):best_pos + 1]
    if best_cat in _POSITIVE and any(f" {n} " in window for n in NEGATORS):
        return "غير معروف", None
    if best_cat == "صدوق" and any(_first_index(text, q) < 10**9 for q in _QUALIFIERS_N):
        best_cat = "صدوق له أوهام"
    return best_cat, RANKS[best_cat]
