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

from app.parsing.html_clean import DIACRITICS_CLASS, flexible_word
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
# a last-resort boundary when no quote and no «… :» were found. Anchored to a word END — no Arabic
# letter follows, **even across a diacritic** — so bare «قال» never matches the «قال» INSIDE the dual
# «قَالَا:»/«قَالُوا:» («حدّثنا A وB قَالَا: حدّثنا [route]…»). The diacritic step is essential: the corpus
# is fully vocalised, and «قَالَا» = قَال + a fatha + alif, so a plain «(?![ء-ي])» passed (the next char
# is a haraka, not a letter) and split inside «قَالَا», stranding the orphan «ـَا:» + the route in the matn.
_SAY = re.compile(
    "(?:%s)(?!%s*[ء-ي])" % ("|".join(flexible_word(w) for w in ("قال", "قالت", "قالوا", "يقول", "تقول")),
                            DIACRITICS_CLASS)
)
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
# A taʿlīq / co-narrator route at the matn HEAD — «[راوٍ]: حدّثني [route] …» — left there when the split
# fired on al-Bukhārī's «وقال الليثُ: حدّثني …» (the «قال» consumed, the name + route stranded in the
# matn). A name (1-4 tokens) + «:» + a transmission verb is distinctive (a real matn never opens so), so
# the route is re-peeled back into the isnad and the body recovered.
_TALIQ_AHEAD = re.compile(
    r"^\W*(?:[^\s:]+\s+){0,3}[^\s:]+\s*:\s*(?:%s)" % "|".join(
        flexible_word(w) for w in ("حدثني", "حدثنا", "أخبرني", "أخبرنا", "أنبأنا", "أنبأني"))
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
    r"أبو عبد الله|قال أبو داود|قال أبو عيسى|تنبيه|انظر|أخرجه|رواه|أخرجاه|احتج|اتفاق|تحفة|الأطراف|"
    r"قلت|على شرط|هذا حديث|هذا إسناد|\(\s*\d"
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
# A circumstantial/temporal STORY opening — «بَيْنَمَا/بَيْنَا … إذْ …» or «لَمَّا [حدث] قال …» — whose
# whole scene is the matn but would otherwise be split at an inner «قال», leaving the setup («بينما
# رسولُ الله ﷺ …»، «لمّا مات إبراهيمُ …») mis-filed in the isnad. Confirmed by a chain «قال» right
# before it («[راوٍ] قال: بينما/لمّا …») or, for بينما, by a following «إذ».
_SCENE = re.compile(
    r"(?<=[\s،؛:])(?:%s)(?=\s)" % "|".join(flexible_word(w) for w in ("بينما", "بينا", "لما"))
)
_IDH = re.compile(r"(?<=[\s،؛:])(?:%s)(?=\s)" % "|".join(flexible_word(w) for w in ("إذ", "اذ")))
# Same «أنّ/أنّه/أنّها» token, but tolerating a trailing comma/semicolon/colon as well as a space
# («… أبي هريرة أنّه، رأى النبيّ ﷺ…») — used ONLY by the late matn-recovery fallback below, so the
# story-detection that reads _ANNA_WORD keeps its stricter whitespace boundary.
_ANNA_MATN = re.compile(
    r'(?<=[\s،؛:«"“])(?:%s)(?=[\s،؛:])' % "|".join(flexible_word(w) for w in ("أن", "أنه", "أنها"))
)
# A further isnad LINK hiding right behind «أنّ» — «أنّ أبا هريرة أخبره»، «أنّ فلانًا حدّثه» — so this
# «أنّ» introduces a *sub-narrator*, not the matn (the 3rd-person أخبره/حدّثه the chain markers omit).
_LINK_AHEAD = re.compile("|".join(flexible_word(w) for w in (
    "أخبره", "أخبرها", "أخبرهم", "أخبرني", "أخبرنا",
    "حدثه", "حدثها", "حدثهم", "حدثني", "حدثنا", "أنبأه", "أنبأنا",
)))
# A back-reference body that is NOT an independent matn — al-Ḥākim's chain-comparison «وأما حديث
# فلان»، «في حديث القبر»، a «بمعنى/نحو/بمثل [حديث] فلان»، «بهذا الإسناد»، «مرّة أخرى». Left matn-less.
_BACKREF = re.compile("^(?:%s)" % "|".join((
    flexible_word("بمعنى"), flexible_word("نحوه"), flexible_word("نحو"),
    flexible_word("بمثله"), flexible_word("بمثل"), flexible_word("بنحوه"),
    flexible_word("بهذا"), flexible_word("بإسناده"), flexible_word("بإسناد"),
    flexible_word("في") + r"\s+" + flexible_word("حديث"),
    flexible_word("وأما") + r"\s+" + flexible_word("حديث"),
    flexible_word("مرة") + r"\s+" + flexible_word("أخرى"),
)))
# The terminal authority — «النبيّ ﷺ» / «رسول الله ﷺ» — after which the matn can begin directly
# («عن النبيّ ﷺ: "إذا استأذنت…"») with neither «قال» nor «أنّ».
_AUTHORITY = re.compile(
    r"(?:%s|%s|%s)\s*(?:ﷺ|%s)" % (
        flexible_word("النبي"), flexible_word("النبى"),
        flexible_word("رسول") + r"\s+" + flexible_word("الله"),
        r"صلى\s+الله\s+عليه\s+و?سلم",
    )
)
# An action verb that governs «عن …» and IS itself the matn — «نَهَى/سُئِل رسولُ الله ﷺ عن …». The
# terminal-authority split takes only «عن …» after «… ﷺ», stranding the verb (the actual prohibition /
# question) in the isnad; when the verb sits right before the authority the matn must start at it.
_ACTION_BEFORE = re.compile(
    r"(?:%s)\s*$" % "|".join(flexible_word(w) for w in
                             ("نهى", "ينهى", "نهانا", "نهي", "سئل", "يسأل")))


# «أنّ [راوٍ] قال: قال رسولُ الله ﷺ …» — a marfūʿ ATTRIBUTION (the narrator quotes the Prophet), NOT a
# scene: the matn is the Prophet's words, taken by the normal «قال …:» split. The tell is the doubled
# standalone «قال[:] قال [رسول الله/النبي]» — both bare (a story's reply is «فقال/وقال», prefixed, and
# excluded by the (?<![ء-ي]) boundary), so a real story «أنّ رجلًا … فقال … فقال النبيّ» is untouched.
_MARFU_ATTR = re.compile(
    r"(?<![ء-ي])(?:%s)\s*[:،]?\s*(?<![ء-ي])(?:%s)\s+(?:%s|%s|%s)" % (
        flexible_word("قال"), flexible_word("قال"),
        flexible_word("رسول") + r"\s+" + flexible_word("الله"),
        flexible_word("النبي"), flexible_word("النبى"),
    )
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
                and not _MARFU_ATTR.search(tail[:120])  # …not «أنّ [راوٍ] قال: قال رسول الله ﷺ …» (attribution)
                and len(_SPEECH.findall(tail)) >= 2):  # …with ≥2 spoken turns — a real story
            return m.start()
    return None


def _scene_start(lead: str) -> int | None:
    """Index where a circumstantial/temporal story opens after the chain — «[راوٍ] قال: بَيْنَمَا/لمّا
    …», or a «بَيْنَمَا … إذْ …» frame — or ``None``.

    The opener must come AFTER chain material (so one inside a narrator's note isn't taken) AND be
    introduced by a chain «قال» right before it (the «قال: scene» that begins the matn — distinguishing
    «[راوٍ] قال: لمّا …» from the Prophet's own «قال رسولُ الله ﷺ: لمّا …», where the matn starts after
    the authority's قال); a «بَيْنَمَا … إذْ …» frame also qualifies without a leading «قال»."""
    for m in _SCENE.finditer(lead):
        if not _TRANSMIT.search(lead[:m.start()]):
            continue
        introduced = _SAY.search(lead[max(0, m.start() - 14):m.start()])
        is_bayna = strip_diacritics(m.group(0)).startswith("بين")
        if introduced or (is_bayna and _IDH.search(lead[m.start():])):
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
        # the collection author's own editorial note after the matn — Abū Dāwūd in his Sunan,
        # al-Tirmidhī («أبو عيسى») in his Jāmiʿ — is never part of the hadith body.
        flexible_word("قال") + r"\s+" + flexible_word("أبو") + r"\s+" + flexible_word("داود"),
        flexible_word("قال") + r"\s+" + flexible_word("أبو") + r"\s+" + flexible_word("عيسى"),
    )),
    re.DOTALL,
)


# A takhrīj / متابعة cross-reference the source appends AFTER the matn — «رواه البخاري»، «أخرجه
# أحمد»، al-Ḥākim's dual «أخرجاه / لم يخرّجاه»، «تابعه فلان». These are notes, not body, but a bare
# «رواه/أخرجه» can also be real matn («أخرجه الله من النار»، «من رواه عنه»), so we trim only on two
# safe tells, neither of which occurs inside a body: (a) the cross-reference OPENS a new sentence (a
# matn-ending . ؟ ! » " ” precedes it), or (b) the verb is followed by a collection/imām name — or
# the unambiguous dual «أخرجاه».
_TAKHRIJ_COLL = "|".join(flexible_word(w) for w in (
    "البخاري", "بخاري", "مسلم", "أحمد", "الترمذي", "النسائي", "النسائى", "ماجه",
    "الشيخان", "الجماعة", "البيهقي", "الطبراني", "الحاكم", "الدارقطني",
))
_TAKHRIJ_RAWA = "(?:و)?(?:%s)" % "|".join(flexible_word(w) for w in ("رواه", "أخرجه", "تابعه"))
_TAKHRIJ_DUAL = "(?:و)?(?:لم\\s+)?(?:%s)" % "|".join(flexible_word(w) for w in ("أخرجاه", "يخرجاه"))
_TAKHRIJ_REF = re.compile(
    "(?:%s).*$" % "|".join((
        r"(?<=[.؟!»\"”])\s*" + _TAKHRIJ_RAWA,                 # (a) opens a new sentence
        r"(?:^|\s)" + _TAKHRIJ_RAWA + r"\s+(?:%s)" % _TAKHRIJ_COLL,  # (b) verb + a collection/imām
        r"(?:^|\s)" + _TAKHRIJ_DUAL,                          # (b) the unambiguous dual «أخرجاه»
    )),
    re.DOTALL,
)


def _trim_grade_tail(matn: str) -> str:
    """Drop a trailing grade («هذا حديث صحيح…» / «على شرط…») or takhrīj / متابعة cross-reference
    («رواه البخاري»، «أخرجاه»…) from a matn, keeping the body intact."""
    matn = _GRADE_TAIL.sub("", matn).strip(_STRIP)
    return _TAKHRIJ_REF.sub("", matn).strip(_STRIP)


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
    """Return ``(isnad, matn, confidence)`` — the matn with its trailing grade tail removed and any
    secondary chain (تحويل ح / a parallel route) that leaked into its HEAD folded back into the isnad.

    A multi-route ḥadīth «… ح حدثنا أبو الزبير عن جابر أنّ رسول الله «…»» splits at the FIRST route's
    boundary, leaving the later route(s) at the start of the matn. When the matn opens with a
    transmission verb, re-split it: the recovered inner matn is the real body. Kept only if it yields
    a non-empty body (never blanks a real matn)."""
    isnad, matn, conf = _split_isnad_matn(text)
    matn = _trim_grade_tail(matn)
    for _ in range(3):                              # peel each leaked route («… ح … ح …», «قال الليث: حدّثني …»)
        if not (_CHAIN_AHEAD.match(matn) or _TALIQ_AHEAD.match(matn)):
            break
        isnad2, matn2, _c = _split_isnad_matn(matn)
        matn2 = _trim_grade_tail(matn2)
        if not matn2 or matn2 == matn:             # no real body recovered → keep what we had
            break
        isnad, matn = f"{isnad} {isnad2}".strip(), matn2
    return isnad, matn, conf


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
        # …and if that first quote sits INSIDE a story — a post-chain «أنّ …» with ≥2 spoken turns, or
        # a temporal «بَيْنَمَا … إذْ …» / «قال: لمّا …» scene — the matn really begins at that opening,
        # not at the quote, so the scene's setup isn't mis-filed as isnad. Take the EARLIEST opening.
        for opening in (_story_start(text[:start]), _scene_start(text[:start])):
            if opening is not None:
                start = min(start, opening)
        matn = _WS.sub(" ", _QUOTE_CHARS.sub(" ", text[start:end + 1])).strip(_STRIP)
        if matn:                       # a real quoted matn
            return text[:start].strip(_STRIP), matn, "quote"
        # else: a stray/unmatched quote (e.g. a trailing ") — ignore it and fall through to the
        # phrase strategies, which run on the full text (still holding the real matn).

    # A temporal scene «[راوٍ] قال: بَيْنَمَا/لمّا …» whose speech carries no quote: the whole scene is
    # the matn, but the last-«قال» split below would drop its setup into the isnad. _scene_start fires
    # only when a chain «قال» introduces it directly, so a «بينما/لمّا» MID-matn isn't taken for the start.
    scene = _scene_start(text)
    if scene is not None:
        body = _WS.sub(" ", _QUOTE_CHARS.sub(" ", text[scene:])).strip(_STRIP)
        if len(body) >= _MIN_MATN:
            return text[:scene].strip(_STRIP), body, "phrase"

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

    # A post-isnad «أنّ …» report with no «قال» — «عن نافع أنّ ابن عمر كان…»، «عن أبي هريرة أنّه رأى
    # النبيّ…»، «عن رسول الله ﷺ: أنّه توضّأ». Split at the FIRST «أنّ/أنّه/أنّها» that sits after the
    # chain and does NOT itself open another link («أنّ فلانًا أخبره»). A LATE fallback: it runs only
    # after every strategy above failed, so it can only fill an otherwise-empty matn, never re-cut one.
    for m in _ANNA_MATN.finditer(text):
        if not _TRANSMIT.search(text[:m.start()]):            # the «أنّ» must come after chain material
            continue
        if _LINK_AHEAD.search(strip_diacritics(text[m.end():m.end() + 110])):  # «أنّ فلان أخبره» → link
            continue
        body = _WS.sub(" ", _QUOTE_CHARS.sub(" ", text[m.start():])).strip(_STRIP)
        if len(body) >= _MIN_MATN:
            return text[:m.start()].strip(_STRIP), body, "anna"

    # The terminal authority introduces the matn directly — «عن النبيّ ﷺ: "إذا استأذنت…"» — with
    # neither «قال» nor «أنّ». Take what follows the LAST «النبيّ ﷺ» / «رسول الله ﷺ», unless it is a
    # back-reference («بمعنى…»، «وأما حديث…») or another chain link. Also a late, empty-only fallback.
    auths = list(_AUTHORITY.finditer(text))
    if auths:
        a = auths[-1]
        body = _WS.sub(" ", _QUOTE_CHARS.sub(" ", text[a.end():])).strip(_STRIP + "؛")
        if len(body) >= _MIN_MATN and not _CHAIN_AHEAD.match(body) and not _BACKREF.match(body):
            # «نَهَى/سُئِل رسولُ الله ﷺ عن …» — a bare «عن …» body means the action verb before the
            # authority is the real matn; start there so the prohibition/question isn't lost to the isnad.
            av = _ACTION_BEFORE.search(text[:a.start()])
            if av and strip_diacritics(body).lstrip().startswith("عن "):
                full = _WS.sub(" ", _QUOTE_CHARS.sub(" ", text[av.start():])).strip(_STRIP + "؛")
                return text[:av.start()].strip(_STRIP), full, "authority"
            return text[:a.end()].strip(_STRIP), body, "authority"

    return text.strip(_STRIP), "", "none"
