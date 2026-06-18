"""Clean the turath.io page markup.

turath page ``text`` is lightly marked-up Arabic. Observed structure (verified on
صحيح البخاري ط التأصيل and others):

* ``<span data-type='title' id=toc-82>…</span>``  → chapter/bab heading.
* ``• [١]``                                       → start of a numbered hadith.
* ``(^١)``                                        → inline footnote reference.
* a line of underscores (``_________``)            → separates body from footnotes.
* ``* [١] [التحفة: ع ١٠٦١٢]``                      → takhrij/atraf note (in footnotes).

These helpers are deliberately small and pure so they are easy to test and reuse.
"""

from __future__ import annotations

import re

# ── Arabic-Indic digits ──────────────────────────────────────────────────────
_DIGIT_MAP = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
_DIGIT_MAP.update({ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")})  # extended/Persian


def arabic_to_western_digits(text: str) -> str:
    return text.translate(_DIGIT_MAP)


def arabic_digits_to_int(text: str) -> int | None:
    digits = "".join(c for c in arabic_to_western_digits(text) if c.isdigit())
    return int(digits) if digits else None


# ── Diacritic-tolerant matching ──────────────────────────────────────────────
# Arabic combining marks ONLY, built from explicit codepoints so the source stays
# ASCII and the class can never accidentally include the letter block (U+0621–U+064A):
#   U+0610–U+061A  Quranic annotation signs
#   U+064B–U+065F  harakat / tanwin / shadda / sukun (+ extensions)
#   U+0670         dagger (superscript) alef
_MARK_RANGES = ((0x0610, 0x061A), (0x064B, 0x065F), (0x0670, 0x0670))
DIACRITICS_CLASS = "[" + "".join(f"{chr(lo)}-{chr(hi)}" for lo, hi in _MARK_RANGES) + "]"


def flexible_word(word: str) -> str:
    """Regex source matching ``word`` even when diacritised (marks between letters)."""
    marks = DIACRITICS_CLASS + "*"
    return marks.join(re.escape(ch) for ch in word) + marks


# ── Markup helpers ───────────────────────────────────────────────────────────
_TITLE_SPAN = re.compile(
    r"<span[^>]*\bdata-type=['\"]title['\"][^>]*>(.*?)</span>", re.DOTALL
)
_ANY_TAG = re.compile(r"<[^>]+>")
_FOOTNOTE_REF = re.compile(r"\(\^\s*[\d٠-٩۰-۹]+\s*\)")
_FOOTNOTE_SEP = re.compile(r"_{4,}")
# Albani-style grade tag, e.g. "<s0> حسن صحيح" — the verdict runs to the line end.
_S0_GRADE = re.compile(r"<s0>\s*([^<\n]+)")
# In-text printed-page anchor, e.g. "⦗٦⦘".
_PAGE_ANCHOR = re.compile(r"⦗[^⦘]*⦘")
_WS = re.compile(r"\s+")
_INLINE_WS = re.compile(r"[ \t]+")


def extract_titles(text: str) -> list[str]:
    """Chapter/bab headings present on the page, in order."""
    return [_WS.sub(" ", m.group(1).strip()) for m in _TITLE_SPAN.finditer(text)]


def remove_title_spans(text: str) -> str:
    return _TITLE_SPAN.sub(" ", text)


def strip_tags(text: str) -> str:
    return _ANY_TAG.sub("", text)


def remove_footnote_refs(text: str) -> str:
    return _FOOTNOTE_REF.sub("", text)


def split_footnotes(text: str) -> tuple[str, str]:
    """Split a page into ``(body, footnotes)`` on the underscore separator.

    The footnotes block holds editorial annotations and takhrij/atraf notes — kept
    out of the hadith text but available for later enrichment.
    """
    match = _FOOTNOTE_SEP.search(text)
    if match:
        return text[: match.start()], text[match.end():]
    return text, ""


def extract_s0_grades(text: str) -> list[str]:
    """Albani-style grade verdicts from ``<s0>`` tags (usually in the footnotes)."""
    return [m.group(1).strip() for m in _S0_GRADE.finditer(text)]


def clean_body(text: str) -> str:
    """Body text with whitespace fully collapsed (headings/tags/footnote refs gone,
    diacritics preserved). Used where line structure does not matter."""
    text = remove_title_spans(text)
    text = strip_tags(text)
    text = remove_footnote_refs(text)
    return _WS.sub(" ", text).strip()


def clean_block(text: str) -> str:
    """Like :func:`clean_body` but **preserves line breaks**, which is required to
    detect line-anchored hadith markers (e.g. ``١ - …``). Also strips ``⦗..⦘`` page
    anchors. Each line is trimmed; spaces/tabs are collapsed within lines."""
    text = remove_title_spans(text)
    text = _PAGE_ANCHOR.sub("", text)
    text = strip_tags(text)
    text = remove_footnote_refs(text)
    text = _INLINE_WS.sub(" ", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip()


def clean_block_marked(text: str, sentinel: str = "\x00") -> tuple[str, list[str]]:
    """Like :func:`clean_block`, but each title span is replaced by ``sentinel`` (its position kept,
    its text out of the body) and the span titles are returned in order. Lets the parser place several
    أبواب within one page's text — so each hadith takes the باب that precedes it, not the last of the
    page — without the heading text leaking into a matn."""
    titles: list[str] = []

    def _repl(m: "re.Match[str]") -> str:
        titles.append(_WS.sub(" ", m.group(1).strip()))
        return f"\n{sentinel}\n"   # own line, so a following line-anchored «• [N]»/«N -» marker still matches

    text = _TITLE_SPAN.sub(_repl, text)
    text = _PAGE_ANCHOR.sub("", text)
    text = strip_tags(text)
    text = remove_footnote_refs(text)
    text = _INLINE_WS.sub(" ", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip(), titles
