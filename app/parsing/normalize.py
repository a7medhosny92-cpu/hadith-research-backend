"""Classical-Arabic text normalisation for indexing and matching.

Two distinct needs:

* :func:`normalize_for_search` — aggressive folding (drop diacritics, unify alef /
  hamza / ya / ta-marbuta) so queries match regardless of orthographic variation.
* :func:`strip_diacritics` — remove only the tashkeel, preserving letter identity,
  for display-friendly text.

Pure-stdlib so it runs anywhere; richer morphology (CAMeL Tools) is optional.
"""

from __future__ import annotations

import re
import unicodedata

# Tashkeel / Quranic annotation marks (harakat, tanwin, shadda, sukun, dagger alef…).
_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۨ-ۭ]")
_TATWEEL = re.compile(r"ـ")            # ـ kashida
_NON_ARABIC_WS = re.compile(r"[^ء-ي٠-٩\s]")
_WS = re.compile(r"\s+")

# Letter-folding applied only for search normalisation.
_FOLD = str.maketrans(
    {
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",  # alef variants → bare alef
        "ى": "ي",                                   # alef maqsura → ya
        "ؤ": "و",                                   # waw with hamza → waw
        "ئ": "ي",                                   # ya with hamza → ya
        "ء": "",                                    # drop standalone hamza
        "ة": "ه",                                   # ta marbuta → ha
        "ـ": "",                                    # tatweel
    }
)


def strip_diacritics(text: str) -> str:
    """Remove tashkeel and tatweel but keep letters as written."""
    text = unicodedata.normalize("NFC", text)
    text = _DIACRITICS.sub("", text)
    text = _TATWEEL.sub("", text)
    return _WS.sub(" ", text).strip()


def normalize_for_search(text: str) -> str:
    """Fold orthographic variation for robust lexical / embedding matching."""
    text = strip_diacritics(text)
    text = text.translate(_FOLD)
    text = _NON_ARABIC_WS.sub(" ", text)
    return _WS.sub(" ", text).strip()


#: Negators that cancel a following verdict — «غير صحيح», «ليس بثقة», «لم يصحّح», «لم
#: يثبت». Folded forms. «لا/ما» are excluded on purpose: they double as ordinary words
#: and appear in positive idioms («لا بأس به»).
NEGATORS = frozenset({"غير", "ليس", "لست", "لسنا", "لم", "لن"})


def negated_before(tokens: list[str], i: int, *, window: int = 2) -> bool:
    """True if a negator appears within ``window`` folded tokens before position ``i``."""
    return any(tokens[j] in NEGATORS for j in range(max(0, i - window), i))
