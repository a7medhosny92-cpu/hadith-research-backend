"""Extract the NAMED critics' appraisals (أقوال الأئمة) from a rijal tarjama body.

A narrator's grade in the great rijal books is not one verdict — it is a dossier of *named*
judgements: «قال ابنُ معين: ثقة، وقال أبو حاتم: لا يُحتجُّ به، وذكره ابنُ حبّان في الثقات». ابن حجر
(تقريب) and الذهبي (الكاشف) distil those; the prose sources (الجرح والتعديل، تهذيب الكمال، الثقات،
لسان/ميزان) report them WITH the names. This helper pulls «critic → verdict» pairs out of a tarjama
body so the «راوٍ» card can show *who* said *what*, not just a single distilled word.

Precision over recall: a pair is kept only when the speaker is a recognised critic (the curated
``CRITICS`` below — so an isnad narrator inside the tarjama is not mistaken for an appraiser) AND the
quote carries an actual grading word (so a biographical aside «قال أبو حاتم: كان بالكوفة» is dropped).
"""

from __future__ import annotations

import re

from app.parsing.normalize import normalize_for_search, strip_diacritics

# Curated أئمة الجرح والتعديل → the distinctive folded token(s) by which their cited name is recognised.
# Containment match: the surface «قال عليُّ بن المديني» contains «المديني» → ابن المديني. Order matters
# only for display (the canonical name on the left is what is shown).
CRITICS: dict[str, tuple[str, ...]] = {
    "ابن معين": ("ابن معين", "يحيى بن معين"),
    "أحمد بن حنبل": ("احمد بن حنبل", "احمد بن محمد بن حنبل"),
    "البخاري": ("البخاري", "محمد بن اسماعيل البخاري"),
    "أبو حاتم الرازي": ("ابو حاتم", "ابي حاتم"),
    "أبو زرعة الرازي": ("ابو زرعة", "ابي زرعة"),
    "النسائي": ("النسائي",),
    "أبو داود": ("ابو داود", "ابي داود"),
    "الترمذي": ("الترمذي",),
    "الدارقطني": ("الدارقطني",),
    "ابن المديني": ("علي بن المديني", "ابن المديني"),
    "ابن حبان": ("ابن حبان", "محمد بن حبان"),
    "العجلي": ("العجلي",),
    "ابن سعد": ("ابن سعد", "محمد بن سعد"),
    "يحيى القطان": ("يحيى القطان", "يحيى بن سعيد القطان"),
    "ابن مهدي": ("ابن مهدي", "عبد الرحمن بن مهدي"),
    "ابن عدي": ("ابن عدي",),
    "الذهبي": ("الذهبي",),
    "ابن حجر": ("ابن حجر", "العسقلاني"),
    "وكيع": ("وكيع",),
    "الشافعي": ("الشافعي",),
    "ابن نمير": ("ابن نمير", "محمد بن عبد الله بن نمير"),
    "العقيلي": ("العقيلي",),
    "الساجي": ("الساجي",),
    "ابن خراش": ("ابن خراش",),
    "يعقوب بن سفيان": ("يعقوب بن سفيان", "الفسوي"),
    "ابن قانع": ("ابن قانع",),
    "أبو أحمد الحاكم": ("ابو احمد الحاكم",),
    "ابن المبارك": ("ابن المبارك",),
    "إسحاق بن راهويه": ("اسحاق بن راهويه", "ابن راهويه"),
    "شعبة": ("شعبة",),
    "مالك": ("مالك بن انس",),
    "ابن عيينة": ("ابن عيينة", "سفيان بن عيينة"),
}
# Folded critic forms, longest first, so «يحيى بن معين» wins over a bare token if both could match.
# normalize_for_search (not just strip_diacritics) so hamza folds — «أبو حاتم» matches the form «ابو حاتم».
_CRITIC_FORMS: list[tuple[str, str]] = sorted(
    ((normalize_for_search(form), canon) for canon, forms in CRITICS.items() for form in forms),
    key=lambda f: -len(f[0]),
)

_GRADE_WORDS = (
    "ثقة", "ثبت", "حافظ", "حجة", "إمام", "صدوق", "لا بأس به", "ليس به بأس", "محله الصدق", "صالح",
    "مقبول", "مستور", "شيخ", "لين", "ضعيف", "ليس بالقوي", "ليس بثقة", "لا يحتج", "لا يكتب حديثه",
    "منكر الحديث", "منكر", "متروك", "ليس بشيء", "كذاب", "وضاع", "يضع", "مجهول", "لا يعرف", "متهم",
)
_GRADE_FOLDED = tuple(normalize_for_search(g) for g in _GRADE_WORDS)

# «قال [critic]: <verdict>» / «وقال … قاله [critic]: …» — the name sits before the colon.
_SAID = re.compile(r"(?:^|[\s،؛.])(?:و?قال|قاله)\s+([^:.\n،؛]{2,45}?)\s*:\s*([^.\n؛]{2,90})")
# «سمعت [critic] يقول: <verdict>»
_HEARD = re.compile(r"سمعت\s+([^:.\n،؛]{2,45}?)\s+يقول\s*:\s*([^.\n؛]{2,90})")
# verb-grade forms: «وثّقه [critic]» / «ضعّفه [critic]» / «كذّبه [critic]» — the verb IS the grade.
_VERB_GRADE = {"وثقه": "وثّقه", "ضعفه": "ضعّفه", "كذبه": "كذّبه", "وهاه": "وهّاه"}
_VERB = re.compile(r"(وثقه|ضعفه|كذبه|وهاه)\s+([^:.\n،؛]{2,45}?)(?=[\s،؛.]|$)")
# «ذكره [critic] في الثقات» — inclusion is itself a توثيق.
_THIQAT = re.compile(r"ذكره\s+([^:.\n،؛]{2,45}?)\s+في\s+الثقات")


def _match_critic(surface: str) -> str | None:
    """The canonical critic whose form is contained in ``surface`` (folded), else ``None``."""
    folded = normalize_for_search(surface)
    for form, canon in _CRITIC_FORMS:           # longest form first
        if form in folded:
            return canon
    return None


def _has_grade(text: str) -> bool:
    folded = normalize_for_search(text)
    return any(g in folded for g in _GRADE_FOLDED)


def extract_appraisals(body: str) -> list[dict]:
    """Ordered, de-duplicated «critic → verdict» appraisals named in a tarjama body.

    Each item: ``{"critic": <canonical name>, "verdict": <quoted text>}``. One per critic (the first
    graded quote attributed to him); only recognised critics with a grading verdict are kept."""
    body = strip_diacritics(body or "")        # the source is vocalised — «قَالَ» must match «قال»
    out: list[dict] = []
    seen: set[str] = set()

    def add(critic: str | None, verdict: str, *, graded: bool = False) -> None:
        verdict = re.sub(r"\s+", " ", verdict).strip(" :،؛.\"«»")
        # _SAID/_HEARD quote free text → require a grading word (drop biographical asides); the
        # constructed verdicts (a وثّق/ضعّف verb, an inclusion in الثقات) are graded by construction.
        if critic and critic not in seen and (graded or _has_grade(verdict)):
            seen.add(critic)
            out.append({"critic": critic, "verdict": verdict})

    for rx in (_SAID, _HEARD):
        for m in rx.finditer(body):
            add(_match_critic(m.group(1)), m.group(2))
    for m in _VERB.finditer(body):
        add(_match_critic(m.group(2)), _VERB_GRADE[strip_diacritics(m.group(1))], graded=True)
    for m in _THIQAT.finditer(body):
        add(_match_critic(m.group(1)), "ذكره في الثقات", graded=True)
    return out
