"""Heuristically split a hadith into إسناد (chain) and متن (text).

This is genuinely fuzzy — there is no markup separating the two — so we layer
robust signals and report a confidence. Later phases refine this with narrator
(rijāl) data and external datasets.

Strategy, in order:
  1. ``quote``  — the matn is the first quoted span ("…" / «…»). Strongest signal.
  2. ``phrase`` — split after the *last* speech-introducer (قال/قالت/يقول … :),
                  which normally introduces the matn at the end of the chain.
  3. ``none``   — no reliable boundary; the whole text is treated as isnad.
"""

from __future__ import annotations

import re

from app.parsing.html_clean import flexible_word

# Opening quote → its matching closer (a symmetric " pairs with the next ").
_CLOSE_FOR = {'"': '"', "«": "»", "“": "”"}
_QUOTE_CHARS = re.compile(r'["«»“”]')
_STRIP = " \t:،.-—\"«»“”"
_WS = re.compile(r"\s+")

_INTRO = re.compile(
    r"(?:%s)\s*:" % "|".join(flexible_word(w) for w in ("قال", "قالت", "قالوا", "يقول", "تقول"))
)
# Same speech-introducers, but WITHOUT requiring the colon (classical texts often omit it):
# a last-resort boundary when no quote and no «… :» were found.
_SAY = re.compile("|".join(flexible_word(w) for w in ("قال", "قالت", "قالوا", "يقول", "تقول")))
# Transmission markers that prove a *chain* is present (so the text is not matn-only). Kept
# distinctive on purpose: «نا/أنا» alone are too short (they hide inside ordinary words like
# «الناس/وأنا»), so we rely on the unambiguous verbs and «عن » between spaces.
_TRANSMIT = re.compile(
    "|".join(flexible_word(w) for w in
             ("حدثنا", "حدثني", "أخبرنا", "أخبرني", "أنبأنا", "أنبأني", "سمعت", "ثنا"))
    + r"|(?:^|\s)عن\s"
)
# Right after a chain «قال», another transmission verb means we're still inside the isnad.
_CHAIN_AHEAD = re.compile(
    r"^\W*(?:%s)" % "|".join(flexible_word(w) for w in
                             ("حدثنا", "حدثني", "أخبرنا", "أخبرني", "أنبأنا", "أنبأني", "ثنا"))
)
_MIN_MATN = 10   # a recovered matn must be at least this many chars to be believable
# «أنّ النبيَّ ﷺ …» / «أنّ رسولَ الله …» introduces a (marfūʿ) matn that carries no «قال».
_ANNA = re.compile(
    r"(?:%s)\s+(?=%s)" % (
        "|".join(flexible_word(w) for w in ("أن", "أنه", "أنها")),
        "|".join(flexible_word(w) for w in ("النبي", "النبى", "نبي", "رسول")),
    )
)
# A gap between two quoted spans that signals the matn has ended and an editor's note /
# takhrij begins — so we do NOT merge the next span into the matn.
_EDITORIAL = re.compile(r"أبو عبد الله|تنبيه|انظر|أخرجه|رواه|أخرجاه|تحفة|الأطراف|قلت|\(\s*\d")


def _quoted_spans(text: str) -> list[tuple[int, int]]:
    """All quoted spans as ``(open_index, close_index)``, pairing each opener with its
    own closer (handles symmetric " and asymmetric «…» / “…”)."""
    spans: list[tuple[int, int]] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in _CLOSE_FOR:
            close = text.find(_CLOSE_FOR[ch], i + 1)
            if close == -1:
                spans.append((i, n))          # unclosed quote — runs to the end
                break
            spans.append((i, close))
            i = close + 1
        else:
            i += 1
    return spans


def split_isnad_matn(text: str) -> tuple[str, str, str]:
    """Return ``(isnad, matn, confidence)`` where confidence is the strategy used."""
    text = text.strip()

    spans = _quoted_spans(text)
    if spans:
        # the matn is the first quoted span, extended over *adjacent dialogue* spans
        # («…» فقال «…»), but stopping at an editorial/takhrij tail so it isn't swallowed.
        start, end = spans[0]
        for open_i, close_i in spans[1:]:
            gap = text[end + 1:open_i].strip()
            if len(gap) <= 40 and not _EDITORIAL.search(gap):
                end = close_i
            else:
                break
        matn = _WS.sub(" ", _QUOTE_CHARS.sub(" ", text[start:end + 1])).strip(_STRIP)
        if matn:                       # a real quoted matn
            return text[:start].strip(_STRIP), matn, "quote"
        # else: a stray/unmatched quote (e.g. a trailing ") — ignore it and fall through to the
        # phrase strategies, which run on the full text (still holding the real matn).

    intros = list(_INTRO.finditer(text))
    if intros:
        cut = intros[-1].end()
        return text[:cut].strip(_STRIP), text[cut:].strip(_STRIP), "phrase"

    # speech-introducer without the colon: split after the LAST «قال…» whose tail is real
    # matn (not another chain link). Recovers chains whose matn carried no quote or colon.
    for m in reversed(list(_SAY.finditer(text))):
        after = text[m.end():].strip(_STRIP)
        if len(after) >= _MIN_MATN and not _CHAIN_AHEAD.match(after):
            return text[:m.start()].strip(_STRIP), after, "phrase"

    # «أنّ النبيَّ ﷺ …» with no «قال» at all: the matn begins at the Prophet reference.
    annas = list(_ANNA.finditer(text))
    if annas:
        after = text[annas[-1].end():].strip(_STRIP)
        if len(after) >= _MIN_MATN:
            return text[:annas[-1].start()].strip(_STRIP), after, "phrase"

    # no transmission marker at all → there is no chain here; the whole text is the matn
    # (e.g. a tied continuation «وكان يأمرني فأتزر…» that shares the previous isnad).
    if not _TRANSMIT.search(text):
        return "", text.strip(_STRIP), "matn-only"

    return text.strip(_STRIP), "", "none"
