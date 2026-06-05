"""A small naḥw (Arabic syntax) layer for the dynamic {topic}.

The template sentences are written with correct iʿrāb (desinential case
endings). The user-supplied topic, however, is inserted bare — so its case
ending must be added according to its syntactic position (e.g. genitive after a
preposition, nominative as a mubtadaʾ). This module assigns that ending for the
common, safe cases and otherwise leaves the word untouched.

It only affects the text sent to TTS (pronunciation); the on-screen caption
strips diacritics anyway.

Agreement (المطابقة) note: a verb/adjective must agree with the topic in gender
and number, and the topic's gender/number is unknown (user-supplied). Rather
than guess it and risk wrong concord (e.g. feminine "القهوة" needs "تعمل", not
"يعمل"), the Arabic templates are written so the topic only ever lands in a
genitive slot after a preposition (عن/في/مع/إلى) — a position that governs no
agreement. So this module only has to supply the case ending, never conjugate.
"""

from __future__ import annotations

from . import i18n

# Particles/adverbs that put the following noun in the genitive (jarr).
_JARR_GOVERNORS = {"عن", "في", "إلى", "الى", "من", "مع", "على", "عند", "حول"}

# Case -> (ending on a definite noun, ending on an indefinite noun/tanwin).
_ENDINGS = {
    "raf": ("ُ", "ٌ"),   # damma,  dammatan
    "nasb": ("َ", "ً"),  # fatha,  fathatan
    "jarr": ("ِ", "ٍ"),  # kasra,  kasratan
}

# Endings we don't safely inflect (long vowels, alef, hamza on the seat...).
_SKIP_LAST = set("اىويآإأؤئء")


def _bare(token: str) -> str:
    return i18n.strip_tashkeel(token)


def case_for_topic(template: str) -> str:
    """Infer the topic's grammatical case from the word right before it."""
    idx = template.find("{topic}")
    if idx < 0:
        return "raf"
    before = template[:idx].strip()
    if not before:
        return "raf"
    prev = _bare(before.split()[-1])
    if prev in _JARR_GOVERNORS:
        return "jarr"
    return "raf"  # default: nominative (mubtadaʾ / ism of a verb)


def inflect(word: str, case: str) -> str:
    """Add the case ending to a topic noun, conservatively.

    Only definite nouns (starting with the article ال) are inflected, where a
    bare short vowel on the last letter is almost always correct. Indefinite
    nouns are left untouched to avoid diptote/tanwin mistakes.
    """
    w = word.strip()
    if not w or i18n._TASHKEEL.search(w):
        return w  # empty or already diacritized -> leave as-is
    if not _bare(w).startswith("ال"):
        return w  # only definite nouns are safe to inflect automatically
    if w[-1] in _SKIP_LAST:
        return w
    return w + _ENDINGS[case][0]


def apply(template: str, topic: str) -> str:
    """Insert the topic with its correct iʿrāb and fix hamzat-al-waṣl liaison."""
    case = case_for_topic(template)
    inflected = inflect(topic, case)
    out = template.replace("{topic}", inflected)
    # A sukūn-final particle before a definite noun (hamzat al-waṣl) takes a
    # connecting kasra: عَنْ الـ -> عَنِ الـ , مِنْ الـ -> مِنِ الـ
    if _bare(inflected).startswith("ال"):
        out = out.replace("عَنْ " + inflected,
                          "عَنِ " + inflected)
        out = out.replace("مِنْ " + inflected,
                          "مِنِ " + inflected)
    return out


def format_text(template: str, lang: str, topic: str | None = None, **kw) -> str:
    """Fill a template; for Arabic apply naḥw iʿrāb to the topic first."""
    if lang == "ar" and topic is not None:
        return apply(template, topic).format(**kw)
    if topic is not None:
        kw["topic"] = topic
    return template.format(**kw)
