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
from functools import lru_cache

# Tashkeel / Quranic annotation marks (harakat, tanwin, shadda, sukun, dagger alef…).
_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۨ-ۭ]")
_TATWEEL = re.compile(r"ـ")            # ـ kashida
_NON_ARABIC_WS = re.compile(r"[^ء-ي٠-٩\s]")
_WS = re.compile(r"\s+")
# Accusative tanwin ending («جابرًا» / «جابراً») — drop the alif so a name cited in the accusative
# («سمعت جابرًا», «رأيت مجاهدًا») matches its base form «جابر»/«مجاهد». Tanwin is always word-final,
# so this never touches a mid-word alif.
_ACCUSATIVE = re.compile("ًا|اً")

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

# Compound proper names written with a VARIABLE internal space — «معدي كرب» / «معد يكرب» / «معديكرب»
# are one name (the Companion المقدام بن معديكرب), but the space lands differently in the chain vs the
# base, so the tokens never match. Fold them to one canonical token (applied post-letter-fold, gated on
# «كرب» so the regex runs only on the rare name).
_COMPOUND = re.compile(r"معدي?\s*ي?كرب")


# These two are pure and get called millions of times on a small set of repeated strings
# (narrator names during graph-building / rijal-matching), so memoise them. A bounded LRU keeps
# memory flat even when they also run over long, mostly-unique matns during parsing/indexing.
@lru_cache(maxsize=1 << 17)
def strip_diacritics(text: str) -> str:
    """Remove tashkeel and tatweel but keep letters as written."""
    text = unicodedata.normalize("NFC", text)
    text = _ACCUSATIVE.sub("", text)
    text = _DIACRITICS.sub("", text)
    text = _TATWEEL.sub("", text)
    return _WS.sub(" ", text).strip()


@lru_cache(maxsize=1 << 17)
def normalize_for_search(text: str) -> str:
    """Fold orthographic variation for robust lexical / embedding matching."""
    text = strip_diacritics(text)
    text = text.translate(_FOLD)
    if "كرب" in text:
        text = _COMPOUND.sub("معديكرب", text)
    text = _NON_ARABIC_WS.sub(" ", text)
    return _WS.sub(" ", text).strip()


def fold_kunya(tokens: list[str]) -> list[str]:
    """Unify the kunya cases أبو/أبا/أبي → «ابو» so «أبو هريرة»/«أبي هريرة» match.

    Exception: «أبي» immediately before «بن» is the *name* أُبَيّ (أُبَيّ بن كعب), not a
    kunya — kept as «ابي» so a real person isn't confused with a kunya «أبو …». Operates
    on already-folded (normalize_for_search) tokens."""
    out: list[str] = []
    for i, t in enumerate(tokens):
        if t in ("ابو", "ابا", "ابي"):
            nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
            out.append("ابي" if (t == "ابي" and nxt == "بن") else "ابو")
        else:
            out.append(t)
    return out


#: Negators that cancel a following verdict — «غير صحيح», «ليس بثقة», «لم يصحّح», «لم
#: يثبت». Folded forms. «لا/ما» are excluded on purpose: they double as ordinary words
#: and appear in positive idioms («لا بأس به»).
NEGATORS = frozenset({"غير", "ليس", "لست", "لسنا", "لم", "لن"})


def negated_before(tokens: list[str], i: int, *, window: int = 2) -> bool:
    """True if a negator appears within ``window`` folded tokens before position ``i``."""
    return any(tokens[j] in NEGATORS for j in range(max(0, i - window), i))
