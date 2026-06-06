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
        isnad = text[:start].strip(_STRIP)
        matn = _WS.sub(" ", _QUOTE_CHARS.sub(" ", text[start:end + 1])).strip(_STRIP)
        return isnad, matn, "quote"

    intros = list(_INTRO.finditer(text))
    if intros:
        cut = intros[-1].end()
        return text[:cut].strip(_STRIP), text[cut:].strip(_STRIP), "phrase"

    return text.strip(_STRIP), "", "none"
