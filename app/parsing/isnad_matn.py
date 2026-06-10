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
from app.parsing.normalize import strip_diacritics

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
# A gap between two quoted spans that signals the matn has ended and an editor's note / takhrij /
# grade begins — so we do NOT merge the next span into the matn. Matched on diacritic-STRIPPED text
# (al-Mustadrak is heavily vocalised, so vocalised «هذا حَدِيث» / «احتَجَّ» must still match).
_EDITORIAL = re.compile(
    r"أبو عبد الله|تنبيه|انظر|أخرجه|رواه|أخرجاه|احتج|اتفاق|تحفة|الأطراف|قلت|على شرط|هذا حديث|هذا إسناد|\(\s*\d"
)
# A quoted span introduced by a reference preposition («… في "المسند الصحيح"», «كتابه "…"») is a
# title/citation in the commentary, not the matn — stops the dialogue-extension at al-Ḥākim's note.
_REF_PREP = re.compile(r"(?:في|من|عن|الى|على|عند|كتاب\w*)\s*$")
# Crossing the *narration* between two spoken spans of one matn («…» فدعا بها فجاءت «…»): we
# step over it unless it is an editorial/takhrij marker or an implausibly long gap.
_MAX_NARRATION_GAP = 220
# Reported-speech turns (قال/فقال/وقال/قالت/يقول…) — used to tell a multi-turn STORY from a
# plain saying.
_SPEECH = re.compile(
    r"(?:^|[\s،؛])(?:ف|و)?(?:%s)" % "|".join(flexible_word(w) for w in ("قال", "قالت", "يقول", "تقول"))
)
# A story matn opens with a post-chain «أنّ …» (e.g. «عن أبيه: أنّ رجلًا أتى النبيّ ﷺ…»).
_ANNA_WORD = re.compile(
    r"(?<=[\s،؛:])(?:%s)(?=\s)" % "|".join(flexible_word(w) for w in ("أن", "أنه", "أنها"))
)


def _story_start(lead: str) -> int | None:
    """Index in ``lead`` where a post-chain *story* matn begins, or ``None``.

    A story is a «أنّ …» (after chain material) whose own tail is **pure narration** — no
    further transmission link — trailed by **two or more** reported-speech turns: «أنّ رجلًا
    أتى النبيّ ﷺ فقال… قال… فقال:», whose first quote is NOT the matn's start, so the man's
    question and the narration would otherwise be mis-filed as isnad. A plain «أنّ النبيّ ﷺ
    قال:» (one turn) — or a nested chain «أنّه سمع فلانًا يقول: سمعت فلانًا…» — is left alone."""
    for m in _ANNA_WORD.finditer(lead):
        tail = lead[m.start():]
        if (_TRANSMIT.search(lead[:m.start()])     # the «أنّ» comes AFTER the chain
                and not _TRANSMIT.search(tail)      # …and what follows is narration, not a nested chain
                and len(_SPEECH.findall(tail)) >= 2):  # …with ≥2 spoken turns — a real story
            return m.start()
    return None


def _speech_before(text: str, i: int, window: int = 40) -> bool:
    """True if a speech introducer (قال/فقال/يقول…) sits just before index ``i`` — so the quote at
    ``i`` is REPORTED speech (the matn), not a bare title/reference quoted in al-Ḥākim's commentary
    («… قد احتج مسلم في "المسند الصحيح"»). Diacritic-tolerant via _SAY (flexible_word)."""
    return bool(_SAY.search(text[max(0, i - window):i]))


# A grade / takhrīj tail the source prints AFTER the matn — al-Ḥākim's «هذا حديث صحيح
# الإسناد ولم يخرّجاه» / «على شرط الشيخين», al-Dhahabī's «[التعليق …]», a «وفي الباب» cross-
# reference — trimmed so a verdict never shows as part of the matn itself.
_GRADE_TAIL = re.compile(
    "(?:%s).*$" % "|".join((
        flexible_word("هذا") + r"\s+" + flexible_word("حديث"),
        flexible_word("هذا") + r"\s+" + flexible_word("إسناد"),
        flexible_word("هذا") + r"\s+" + flexible_word("خبر"),
        flexible_word("على") + r"\s+" + flexible_word("شرط"),
        r"\[\s*" + flexible_word("التعليق"),
        flexible_word("تلخيص") + r"\s+" + flexible_word("الذهبي"),
        flexible_word("وفي") + r"\s+" + flexible_word("الباب"),
    )),
    re.DOTALL,
)


def _trim_grade_tail(matn: str) -> str:
    """Drop a trailing «هذا حديث صحيح…» / «على شرط…» grade or takhrīj note from a matn."""
    return _GRADE_TAIL.sub("", matn).strip(_STRIP)


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
    """Return ``(isnad, matn, confidence)`` — the matn with any trailing grade tail removed."""
    isnad, matn, conf = _split_isnad_matn(text)
    return isnad, _trim_grade_tail(matn), conf


def _split_isnad_matn(text: str) -> tuple[str, str, str]:
    """Return ``(isnad, matn, confidence)`` where confidence is the strategy used."""
    text = text.strip()

    spans = _quoted_spans(text)
    # The matn quote must be SPEECH-INTRODUCED («… قال/فقال: "…"»). A bare quoted title / reference in
    # al-Ḥākim's commentary («قد احتج مسلم في "المسند الصحيح"») is NOT the matn — starting blindly at
    # the first quote either took it whole (losing the real unquoted matn) or merged it on. So begin
    # at the first SPEECH-introduced quote.
    first = next((k for k, (a, _b) in enumerate(spans) if _speech_before(text, a)), None)
    if first is not None:
        # that quoted span, extended over the *dialogue / narration* of one story («…» فدعا بها
        # فجاءت «…»), but stopping at an editorial/takhrij tail or a title/citation in commentary.
        start, end = spans[first]
        for open_i, close_i in spans[first + 1:]:
            gap = text[end + 1:open_i].strip()
            bare = strip_diacritics(gap)
            if _EDITORIAL.search(bare) or _REF_PREP.search(bare) or len(gap) > _MAX_NARRATION_GAP:
                break
            end = close_i
        # …and if that first quote sits INSIDE a story (a post-chain «أنّ …» with ≥2 spoken
        # turns ahead of it), the matn really begins at the «أنّ», not at the quote.
        story = _story_start(text[:start])
        if story is not None:
            start = story
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
