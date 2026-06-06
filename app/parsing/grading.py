"""Detect an explicit authenticity grade (حكم) in hadith text.

Many editions (e.g. al-Albānī, al-Arnaʾūṭ) print a ruling next to the hadith:
``إسناده صحيح``, ``حديث حسن صحيح``, ``[ضعيف]``, ``قال الترمذي: حسن`` …

We only match a grade when it sits in a *grading context* (after إسناد/حديث/حكم,
a ``قال …:`` attribution, or in brackets) to avoid matching the word صحيح where it
merely occurs in the matn. Returns the normalised grade or ``None``.
"""

from __future__ import annotations

import re

from app.parsing.html_clean import DIACRITICS_CLASS, flexible_word

# Order matters: longer / more specific grades first.
_GRADES = ["حسن صحيح", "صحيح لغيره", "حسن لغيره", "ضعيف جدا", "صحيح", "حسن", "ضعيف",
           "موضوع", "منكر", "شاذ", "متروك"]
_GRADE_ALT = "|".join(flexible_word(g) for g in _GRADES)

# A grade preceded by a grading-context cue. «حديث» must carry a demonstrative
# («هذا حديث حسن صحيح» — al-Tirmidhī's formula) so a bare «حديث حسن» *inside the matn*
# (or a bab title) isn't read as a ruling.
_HADITH_RULING = "(?:%s)\\s+%s" % (
    "|".join(flexible_word(d) for d in ("هذا", "وهذا", "فهذا")), flexible_word("حديث")
)
_CTX = re.compile(
    r"(?:%s|%s|%s|قال[^:]{0,25}:)\s*[«\"]?(%s)"
    % (flexible_word("إسناده"), _HADITH_RULING, flexible_word("حكم"), _GRADE_ALT)
)
# … or a bracketed ruling like [صحيح] / (ضعيف).
_BRACKET = re.compile(r"[\[(]\s*(%s)\s*[\])]" % _GRADE_ALT)
# A bare grade token, for text that is ALREADY a ruling (e.g. an <s0> grade tag).
_RULING = re.compile(r"(%s)" % _GRADE_ALT)

_MARKS = re.compile(DIACRITICS_CLASS)
_WS = re.compile(r"\s+")


def _clean(grade: str) -> str:
    return _WS.sub(" ", _MARKS.sub("", grade)).strip()


def extract_grade(text: str) -> str | None:
    """Find an authenticity grade that sits in a grading *context* (see module doc)."""
    for pattern in (_BRACKET, _CTX):
        match = pattern.search(text)
        if match:
            return _clean(match.group(1))
    return None


def grade_in_ruling(text: str | None) -> str | None:
    """Normalise a grade from text that is itself a ruling (no context needed),
    e.g. the contents of an ``<s0>`` grade tag like ``حسن صحيح``."""
    if not text:
        return None
    match = _RULING.search(text)
    return _clean(match.group(1)) if match else None
