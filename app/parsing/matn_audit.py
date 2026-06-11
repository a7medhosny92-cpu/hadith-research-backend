"""Audit every matn for likely extraction errors — the متن counterpart of ``scripts.audit_isnad``.

``split_isnad_matn`` is heuristic, so this flags the ways its output can be wrong. Every matn is
CHECKED (deterministic, free, on every build) and the suspect ones surface for review / the faithful
LLM ``--mode chains`` repair — exactly like «التدقيق» does for isnads. Each hit is a *candidate*, never
a verdict.

  V  متنٌ مفقود أو مبتور — the matn is empty or a fragment though the ḥadīth has a real body that
      stayed in the isnad (the «detti non completi» class — al-Mustadrak #7514 showed «ادع تلك الشجرة»
      with the whole story dumped into the isnad).
  I  أداة إسناد في المتن — a transmission verb (حدثنا/أخبرنا…) or a leading «عن فلان» leaked into the matn.
  G  حكمٌ/تخريجٌ في المتن — a grade / takhrīj / editorial tail sits inside the matn («هذا حديث صحيح»،
      «على شرط»، «رواه/أخرجه»، «قال أبو داود»…).
  Q  ليس متنًا — the matn is only a Qurʾān verse ﴿…﴾ or a chapter heading (باب/كتاب), no ḥadīth body.

Calibrated to be **high-precision** (a complete short matn like «إنما الأعمال بالنيات» must NOT flag);
thresholds (V's word counts) are the obvious tuning knob once measured on the real corpus.
"""

from __future__ import annotations

import re

from app.parsing.normalize import normalize_for_search

LABELS = {
    "V": "متنٌ مفقود أو مبتور (المتن في الإسناد غالبًا)",
    "I": "أداةُ إسنادٍ في المتن (تسرَّب الإسناد)",
    "G": "حكمٌ أو تخريجٌ في المتن",
    "Q": "ليس متنًا (آيةٌ فقط أو عنوان باب)",
}

# Clear narration-TO verbs — pure isnad, they never open a matn (matched on the folded text).
_CHAIN_VERB = re.compile(r"(?:^|\s)(?:حدثنا|حدثني|اخبرنا|اخبرني|انبانا|انباني|ثنا)(?=\s|$)")
# A matn that OPENS with «عن فلان» is isnad that spilled past the split point.
_STARTS_AN = re.compile(r"^عن\s")
# Grade / takhrīj / editorial that belongs AFTER the matn, not inside it (folded forms).
_EDITORIAL = re.compile(
    r"هذا\s+حديث|هذا\s+اسناد|هذا\s+خبر|علي\s+شرط|اخرجه(?!\s+الله)|اخرجاه|رواه(?!\s+عنه)|وفي\s+الباب|"
    r"قال\s+ابو\s+داود|قال\s+ابو\s+عيسي|تلخيص\s+الذهبي"
)
# A chapter heading mistaken for a matn (a bare «باب …» line).
_HEADING = re.compile(r"^(?:باب|كتاب|فصل|جماع)(?=\s|$)")
# Back-references that legitimately carry (almost) no matn of their own — never an empty-matn error.
_BACKREF = re.compile(
    r"نحوه|مثله|بمثله|بنحوه|نحو\s+ذلك|مثل\s+ذلك|فذكر|بهذا|باسناده|بسنده|بمعناه|الحديث$"
)
_VERSE_SPAN = re.compile(r"﴿[^﴾]*﴾")           # a whole Qurʾān-verse span ﴿…﴾
_VERSE = re.compile(r"[﴾﴿]")
_QUOTE = re.compile(r'[«"“]')                   # a quoted span still sitting in the isnad
_TOK = re.compile(r"\S+")


def _nwords(text: str) -> int:
    return len(_TOK.findall(text))


def flag_matn(matn: str, isnad: str, chapter: str = "") -> list[tuple[str, str]]:
    """Return ``(code, detail)`` flags for one extracted matn; empty when it looks clean."""
    m = (matn or "").strip()
    isn = (isnad or "").strip()
    mn = normalize_for_search(m)
    isn_n = normalize_for_search(isn)
    out: list[tuple[str, str]] = []
    mw, iw = _nwords(mn), _nwords(isn_n)
    backref = bool(_BACKREF.search(mn) or _BACKREF.search(isn_n))

    # V — empty/fragment matn on a ḥadīth that clearly has a body: an EMPTY matn beside a non-short
    # isnad, OR a tiny matn while the isnad still holds a quoted span (the spoken text the split
    # should have taken). Genuine back-references (نحوه / بهذا الإسناد) are excepted.
    if not backref and ((mw == 0 and iw >= 6) or (mw <= 3 and iw >= 8 and _QUOTE.search(isn))):
        out.append(("V", f"متنٌ من {mw} كلمة مع إسنادٍ من {iw} كلمة"))

    # I — a narration verb at the matn's HEAD, or a leading «عن فلان», = isnad spilled past the
    # boundary. A chain verb DEEP in the matn is reported speech («فقال: إنّ جبريل أخبرني»، «قال
    # فلان: حدّثني») or a Bukhārī muʿallaq tail — not a head-leak; and a back-reference («… بهذا
    # الإسناد مثله») is a corroborating chain with no body of its own. Both are excepted.
    head = " ".join(mn.split()[:2])
    if not backref and (_CHAIN_VERB.search(head) or _STARTS_AN.search(mn)):
        out.append(("I", "في المتن أداةُ إسناد (حدثنا/أخبرنا أو «عن فلان» في أوله)"))

    # G — a grade / takhrīj / editorial note inside the matn. «أخرجه الله» / «رواه عنه» are real body
    # (God «brought out», a hadith his companions «narrated»), not a takhrīj — excepted.
    if _EDITORIAL.search(mn):
        out.append(("G", "في المتن حكمٌ/تخريجٌ (هذا حديث/على شرط/رواه/قال أبو داود…)"))

    # Q — a chapter heading, or ONLY a Qurʾān verse with no ḥadīth body around it (a matn that merely
    # quotes a verse, with a real body, is fine).
    if _HEADING.search(mn):
        out.append(("Q", "عنوان باب/كتاب لا متن"))
    elif _VERSE.search(m) and _nwords(normalize_for_search(_VERSE_SPAN.sub(" ", m))) <= 3:
        out.append(("Q", "آيةٌ قرآنية بلا متن حديث"))

    return out
