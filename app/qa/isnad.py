"""Structural analysis of an isnad (chain of narrators).

We parse the chain into an ordered list of narrators by splitting on the classical
transmission terms (حدثنا، أخبرنا، عن، سمعت…), then flag features that matter to
hadith critics: the transmission mode of each link (سماع vs عنعنة), تحويل (ح) when
multiple chains merge, and whether the chain reaches the Prophet ﷺ.

This is a *structural* read, not an authenticity verdict: grading the narrators
themselves needs a rijal (narrator-biography) database — see the note in the
output. That database is the cat-26 corpus, a planned ingestion step.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from app.parsing.normalize import normalize_for_search, strip_diacritics
from app.rijal.graph import is_prophet
from app.rijal.index import _clean_tokens, from_companion_dictionary

if TYPE_CHECKING:
    from app.rijal import RijalIndex, RijalMatch
    from app.rijal.canon import Canonicalizer

# Transmission terms → mode. Keys are in the folded form of normalize_for_search.
_VIA: dict[str, str] = {
    "حدثنا": "سماع", "حدثني": "سماع", "حدثناه": "سماع", "ثنا": "سماع", "نا": "سماع",
    "اخبرنا": "سماع", "اخبرني": "سماع", "اخبرناه": "سماع", "انبانا": "سماع", "انباني": "سماع",
    "سمعت": "سماع", "سمعنا": "سماع", "سمع": "سماع", "سمعه": "سماع",
    "سمعته": "سماع", "سمعتها": "سماع", "سمعتهم": "سماع", "سمعتهما": "سماع",
    "اخبركم": "سماع", "اخبركما": "سماع", "اخبرتكم": "سماع", "حدثكما": "سماع", "حدثتكم": "سماع",
    # Object-pronoun transmission forms: here the شيخ comes BEFORE the verb, in the topicalised
    # «(أنّ) الزهري أخبره أنّ …» / «أبا سلمة حدّثه». The verb must CLOSE the شيخ's name — without it
    # «أخبره/حدثه/أنبأه» glue onto it, forging bogus narrator nodes like «الزهري أخبره» (which then
    # aggregate the real man's whole network). isnad_matn._LINK_AHEAD already recognises this set.
    "اخبره": "سماع", "اخبرها": "سماع", "اخبرهم": "سماع", "اخبرهما": "سماع",
    "حدثه": "سماع", "حدثها": "سماع", "حدثهم": "سماع", "حدثهما": "سماع",
    "انباه": "سماع", "انباها": "سماع", "انباهم": "سماع",
    # 1st/3rd-person + plural transmission forms the terse list missed (found by scripts.audit_nodes):
    # «حدّثتني», «حدّثكم», «أخبرتني», «سمعوا» — each a سماع verb that must close the surrounding name.
    "حدثتني": "سماع", "حدثتنا": "سماع", "حدثكم": "سماع", "حدثت": "سماع",
    "اخبرتني": "سماع", "اخبرتنا": "سماع", "اخبرتها": "سماع", "اخبرت": "سماع",
    "سمعوا": "سماع", "سمعوه": "سماع", "حدث": "سماع", "اخبر": "سماع", "انبا": "سماع", "نبا": "سماع",
    # قراءة / عرض (a mode of تحمّل): «قرأت على مالك», «عرض عليه», «قُرئ على فلان». These take a following
    # «على/عليه» (the شيخ's preposition) which must be skipped, never read as the name علي — see _QIRAA.
    "قرات": "سماع", "قرا": "سماع", "قراه": "سماع", "قرانا": "سماع", "اقراه": "سماع", "اقرات": "سماع",
    "قرئ": "سماع", "قري": "سماع", "عرض": "سماع", "عرضت": "سماع", "عرضنا": "سماع", "عرضوا": "سماع",
    "عرضتم": "سماع", "عرضه": "سماع",
    "عن": "عنعنة", "عنه": "عنعنة",
}
# قراءة/عرض verbs are followed by «على/عليه» (the شيخ's preposition) — skipped in the loop so it
# never becomes the name «علي» (folded identically). Kept apart from _VIA only to flag the skip.
_QIRAA = {"قرات", "قرا", "قراه", "قرانا", "اقراه", "اقرات", "قرئ", "قري",
          "عرض", "عرضت", "عرضنا", "عرضوا", "عرضتم", "عرضه"}
_DIGITS = re.compile(r"[0-9٠-٩۰-۹]")   # footnote-superscript / hadith-number digits glued onto a name
# Connective words that are not narrator names. «بهذا/بهذه» introduces a back-reference
# («بهذا الإسناد») — dropped so «الإسناد» (a hard matn marker below) cleanly ends the chain.
_SKIP = {"قال", "قالا", "قالوا", "يعني", "قالت", "ح", "بهذا", "بهذه"}
# Matn-start markers: once the isnad reaches one of these (after a narrator) the matn
# has begun and the chain ends. «قال/قالت» are *soft* — a boundary only when NOT followed
# by a transmission verb (… قال حدثنا … keeps going); the rest always begin the matn.
_MATN_HARD = {"مرفوعا", "رفعه", "يرفعه", "نحوه", "مثله", "بنحوه", "بمثله", "بمعناه", "بمعنى",
              # back-reference to a previously-given chain («… بهذا الإسناد / بإسناده / بسنده»), or an
              # abbreviated matn «… فذكر الحديث / فذكره»: the report follows — stop the chain.
              "الاسناد", "اسناده", "باسناده", "بسنده", "باسناد", "فذكر", "فذكره"}
# «قال/يقول/فقال…» are *soft*: a boundary only when NOT followed by a transmission verb. «X يقول:
# سمعت Y», «سألت X فقال: حدثني Y» CONTINUE the chain (X reports hearing the next narrator) — making
# يقول/فقال hard truncated «علقمة … يقول: سمعت عمر» and «… فقال: حدثني عبد الله», dropping the صحابي.
_MATN_SOFT = {"قال", "قالت", "يقول", "تقول", "فقال", "فقالت", "فقالوا", "يقولون"}
# Action verbs that open a narrated scene («كان رسول الله ﷺ يخطب / يصلّي / يدعو …», «سمعته
# يحدّث …»): treated like a soft boundary — the matn begins UNLESS a transmission verb
# follows (… يحدّث عن أبيه … keeps the chain), so a real «سمعته يحدّث عن فلان» is never truncated.
_MATN_VERB = {"يخطب", "يصلي", "يدعو", "يقرا", "يكبر", "يامر", "يحدث", "يذكر", "يصنع", "يفعل",
              # narrative-scene openers «كان رسول الله ﷺ …», «رأيت/دخلت/خرجت/سألت …» (audit_nodes)
              "كان", "رايت", "دخل", "خرج", "سال", "سالت", "سالنا"}
# «أنّ / أنّه / أنّها» opens the report (matn) — «… عن ابن عمر أنّ رسول الله ﷺ قال …».
# If its subject is the Prophet the chain is marfūʿ and he is the terminal narrator;
# otherwise the report has begun and the chain ends. (Without this, «أن رسول الله» glued
# onto the previous name, making bogus nodes like «ابن عمر أن رسول الله ﷺ».)
_MATN_ANNA = {"ان", "انه", "انها", "انهم", "انهما", "انهن"}   # incl. dual/plural «أنّهما/أنّهم» co-narrators
_PROPHET_HEAD = {"النبي", "نبي", "رسول"}
# Tokens still inside a Prophet reference (his name + the eulogy); the first token
# outside this set ends the Prophet's (terminal) name and starts the matn.
_EULOGY = {"النبي", "نبي", "رسول", "الله", "صلي", "عليه", "وسلم", "واله", "وصحبه", "سلم"}
# A waw on a name token joins TWO co-narrators («الزهري وهشام بن عروة» = al-Zuhrī AND Hishām, both from
# ʿUrwa) — they must be SPLIT into two nodes, not fused into one «الزهري وهشام بن عروة» (which corrupts the
# graph + the documented network). But a leading waw is also the start of real names (وكيع، وهب) and the
# waw can sit INSIDE a name after a joiner (أبو وائل، عبد الله بن وهب) — those must NOT split.
_NAME_JOINERS = {"بن", "ابن", "ابو", "ابا", "ابي", "ام", "عبد", "عبيد", "ذو", "ذي",
                 "اخو", "اخي", "بنت", "ابنه", "مولي", "ابناء"}
_WAW_NAMES = {"وكيع", "وهب", "وهيب", "واصل", "وضاح", "ورقا", "وايل", "وبره", "وردان",
              "ورد", "وازع", "واقد", "وبر", "وهبان", "وثيمه", "ورقاء"}
# Waw-words that are NOT a co-narrator: pronouns, matn verbs, aggregators («فلان وكلاهما/وغيره») —
# the remainder after the waw is not a name, so these must never trigger a split.
_WAW_STOP = {"وهو", "وهي", "وهم", "وهما", "وغير", "وغيره", "وغيرها", "وغيرهم", "واخر", "واخرون",
             "واخرين", "وذكر", "وذكره", "وكان", "وكانت", "وقال", "وقالت", "وقالوا", "ونحوه",
             "ونحوها", "وزاد", "وزادني", "وحده", "وفيه", "وفيها", "وكذا", "وكذلك", "ولفظه",
             "وهذا", "وكلاهما", "وكلهم", "وجميعا", "ومن", "وفي", "وقد"}
_TOKEN = re.compile(r"[^\s،,.:؛()«»\"']+")


@dataclass(slots=True)
class Narrator:
    name: str
    via: str  # سماع | عنعنة | — (chain head)


@dataclass(slots=True)
class IsnadAnalysis:
    narrators: list[dict]
    length: int
    modes: dict[str, int]
    has_tahwil: bool          # ح — more than one route
    has_anana: bool           # عن — possible tadlīs, needs samāʿ confirmed
    reaches_prophet: bool
    notes: list[str]
    rijal_assessment: dict | None = None  # narrator gradings, when a RijalIndex is supplied

    def to_dict(self) -> dict:
        return asdict(self)


# Unnamed (مبهم) narrators are a real جهالة (a defect in the text itself), not a gap in our
# database: «عن رجلٍ»، «شيخٍ له»، «عمّن حدّثه»، «بعض أصحابه»، «فلان». An *unnamed Companion*
# («رجلٌ من أصحاب النبي ﷺ») is excepted — the Companions are عدول even when unnamed.
_MUBHAM_BARE = {"رجل", "رجلا", "امراه", "امراة", "شيخ", "فلان", "علان"}
_MUBHAM_PHRASE = re.compile(r"بعض|لم يسم|عمن")


def _is_mubham(name: str) -> bool:
    """Is this an *unnamed* narrator (إبهام) — a genuine جهالة, not merely unknown to us?"""
    toks = normalize_for_search(name).split()
    if not toks:
        return False
    if any(t in ("النبي", "نبي", "رسول") for t in toks):
        return False    # «… من أصحاب النبي ﷺ» — an unnamed Companion, acceptable
    return toks[0] in _MUBHAM_BARE or bool(_MUBHAM_PHRASE.search(" ".join(toks)))


def _chain_assessment(matches: list["RijalMatch | None"], total: int, mubham: int = 0) -> dict:
    """Summarise the chain from its narrator gradings — verdict by the weakest link."""
    ranks = [m.entry.rank for m in matches if m and m.entry.rank is not None]
    known = sum(1 for m in matches if m)
    unknown = total - known
    weakest = min(ranks) if ranks else None

    if weakest is None:
        verdict = "لم يُعرف رواة هذا الإسناد في قاعدة الرجال (القاعدة محدودة)."
    elif weakest <= 1:
        verdict = "في الإسناد راوٍ متروك أو متّهم؛ ضعيف جدًا."
    elif weakest == 2:
        verdict = "في الإسناد راوٍ ضعيف."
    elif weakest <= 4:
        verdict = "في الإسناد راوٍ مجهول أو ليّن الحديث."
    elif weakest <= 6:
        verdict = "في الإسناد من لا يُحتجّ بتفرّده (مقبول/صدوق له أوهام)."
    elif unknown == 0:
        verdict = "رجال الإسناد كلّهم ثقات أو أثبات بحسب القاعدة."
    else:
        verdict = f"مَن عُرف منهم ثقات؛ وبقي {unknown} راوٍ لم يُعرفوا في القاعدة."
    if mubham:
        verdict = f"{verdict} وفيه {mubham} راوٍ مبهمٌ لم يُسمَّ (جهالة)."
    return {"weakest_rank": weakest, "known": known, "unknown": unknown,
            "mubham": mubham, "verdict": verdict}


def analyze_isnad(
    text: str, rijal: "RijalIndex | None" = None, canon: "Canonicalizer | None" = None,
    muhmal: "dict[str, str] | None" = None, network: "DocumentedNetwork | None" = None,
    split_conarrators: bool = False,
) -> IsnadAnalysis:
    raw = strip_diacritics(text or "")
    narrators: list[Narrator] = []
    via: str | None = None
    buf: list[str] = []
    has_tahwil = False
    # Indices that begin a NEW route after a تحويل (ح). The narrator before a ح seam and the
    # one after it belong to different chains — they are neither a real تلميذ→شيخ link nor each
    # other's disambiguation context, so these indices are excluded from both below.
    route_starts: set[int] = set()
    pending_break = False
    pending_ala = False           # the previous token was a قراءة verb → skip its «على/عليه»

    def flush() -> bool:
        nonlocal pending_break
        name = " ".join(buf).strip(" -،")
        if name:
            narrators.append(Narrator(name=name, via=via or "—"))
            if pending_break:
                route_starts.add(len(narrators) - 1)
                pending_break = False
            return is_prophet(name)   # the Prophet is terminal — nothing narrates from him
        return False

    # strip footnote-superscript / hadith-number digits glued onto tokens («الله١»→«الله», «حدثنا١»→
    # «حدثنا», «م ٢»→«م» then dropped) before they corrupt a node — names never carry a digit.
    tokens = [t for t in (_DIGITS.sub("", t) for t in _TOKEN.findall(raw)) if t]
    for i, token in enumerate(tokens):
        folded = normalize_for_search(token)
        nxt = normalize_for_search(tokens[i + 1]) if i + 1 < len(tokens) else ""
        if pending_ala:                       # «قرأت/عرضت [على/عليه] فلان» — drop the قراءة preposition
            pending_ala = False               # (folds to «علي»; must not be read as the name)
            if folded in ("علي", "عليه"):
                continue
        if folded == "ح":
            has_tahwil = True       # تحويل: a standalone ح switches to another route, so
            flush()                 # finalise this route's last narrator and mark the next one
            pending_break, buf = True, []   # as a new route (the ح seam isn't a real link)
            continue
        # a hadith number («م - ٢٣٤٥»), a lone ramz letter (خ م د ت س ق …) or bare punctuation
        # is never a narrator name — drop it before it glues onto the surrounding name.
        if not folded or folded.isdigit() or len(folded) == 1:
            continue
        # accept a leading و (وحدثنا، وعن، وأخبرنا …)
        conn = folded if folded in _VIA else (
            folded[1:] if folded[:1] == "و" and folded[1:] in _VIA else None
        )
        if conn:
            if flush():           # reached the Prophet → stop; the matn follows
                break
            via, buf = _VIA[conn], []
            pending_ala = conn in _QIRAA      # a قراءة verb → its next «على/عليه» is a preposition
            continue
        # «أنّ» opens the report: end the current narrator. If it is about the Prophet
        # («… أنّ رسول الله ﷺ قال») the chain is marfūʿ and he is the terminal narrator;
        # otherwise the report (matn) has begun → stop.
        if folded in _MATN_ANNA or (folded[:1] == "و" and folded[1:] in _MATN_ANNA):
            if flush():
                break
            if nxt in _PROPHET_HEAD:
                via, buf = None, []
                continue
            break
        # matn boundary: the isnad ends where the report (matn) begins
        nxt_is_via = nxt in _VIA or (nxt[:1] == "و" and nxt[1:] in _VIA)
        soft = folded in _MATN_SOFT or folded in _MATN_VERB
        if folded in _MATN_HARD or (soft and not nxt_is_via):
            flush()
            break
        if soft:   # «قال حدثنا …» / «سمعته يحدّث عن …» — connective, not the matn; drop it
            continue
        # co-narrator waw: «A وB …» lists two narrators sharing the next شيخ; split so B is its OWN
        # clean node, not fused into «A وB». This is a GRAPH-HYGIENE operation (de-fuse the node for
        # the network / «راوٍ» card), gated to graph-build: in the VERDICT path it would surface the
        # newly-separated bare ism as ambiguous (A↑) and trip the deep-صحابي flag on a Companion
        # co-narrator (S↑), so the audit/verify keep the old segmentation. Fire only on a COMPLETE
        # name (prev token not a name-joiner بن/أبو) when «وX» is not itself a name (وكيع/وهب), an
        # eulogy (وسلم), or a matn/aggregator word (وكان/وغيره).
        if (split_conarrators and buf and folded[:1] == "و" and len(folded) > 3
                and folded not in _WAW_NAMES and folded not in _EULOGY and folded not in _WAW_STOP
                and normalize_for_search(buf[-1]) not in _NAME_JOINERS):
            flush()                            # finalise A (the man before the waw)
            pending_break = True               # B begins a new route → no false A→B link / company
            buf = [token[1:]]                  # …and starts with the de-waw'd name (وهشام → هشام)
            continue
        # the Prophet is the terminal narrator: once the buffer is the Prophet and the
        # next token isn't part of the eulogy, the matn has begun
        if buf and folded not in _EULOGY and is_prophet(" ".join(buf)):
            flush()
            break
        if folded in _SKIP:
            continue
        buf.append(token)
    else:
        flush()

    modes: dict[str, int] = {}
    for narrator in narrators:
        if narrator.via in ("سماع", "عنعنة"):
            modes[narrator.via] = modes.get(narrator.via, 0) + 1
    has_anana = modes.get("عنعنة", 0) > 0
    # marfūʿ iff the chain actually ends at the Prophet (not merely mentions him in matn)
    reaches_prophet = bool(narrators) and is_prophet(narrators[-1].name)

    # The Companion sits at the END of the chain (he narrates from the Prophet ﷺ); the terminal
    # index is the last non-Prophet narrator — used to prefer a صحابي reading there (تمييز بالطبقة).
    terminal_idx = len(narrators) - 2 if (narrators and is_prophet(narrators[-1].name)) else len(narrators) - 1

    # تمييز المهمل بالشيخ والتلميذ (the joint resolver) — a chain-level pre-pass, only when a
    # DOCUMENTED network is loaded. Anchor the links we are sure of (a unique-name match) and let
    # `resolve_chain` propagate: an ambiguous link is fixed to the homonym DOCUMENTED as a تلميذ of
    # its resolved شيخ (or شيخ of its resolved تلميذ). It only ANCHORS on confident identities and
    # resolves by positive evidence — so it CANNOT override a confident match (it produces an answer
    # only for links the name alone left ambiguous), and a non-unique link stays held. Used below as
    # the LAST تمييز lever, after muhmal/canon, never before them.
    joint: list[str | None] = [None] * len(narrators)
    if network and rijal is not None and len(narrators) > 1:
        from app.rijal.resolve import resolve_chain
        cand_lists: list[list[str]] = []
        anchors: list[str | None] = []
        for nar in narrators:
            if is_prophet(nar.name) or _is_mubham(nar.name):
                cand_lists.append([]); anchors.append(None); continue
            m = rijal.lookup(nar.name)
            if m is not None and m.score >= 1.0 and not m.ambiguous:   # a confident identity → anchor
                anchors.append(m.entry.name); cand_lists.append([m.entry.name])
            else:
                anchors.append(None)
                cand_lists.append([c.name for c in
                                   rijal.candidates(nar.name, apply_prominence=False, max_results=None)])
        joint = resolve_chain(cand_lists, anchors, network, route_starts)

    narrator_dicts: list[dict] = []
    matches: list["RijalMatch | None"] = []
    mubham_count = 0
    for i, narrator in enumerate(narrators):
        record = asdict(narrator)
        prophet = is_prophet(narrator.name)
        mubham = (not prophet) and _is_mubham(narrator.name)
        record["is_prophet"] = prophet
        record["mubham"] = mubham
        if i in route_starts:
            record["route_start"] = True   # begins a new route after a ح — no link from the prior man
        if mubham:
            mubham_count += 1
        if rijal is not None:
            # the Prophet ﷺ is the source, and a مبهم has no name to look up — neither is
            # graded (the Prophet would else match a Companion; the مبهم is a جهالة by itself).
            if prophet or mubham:
                match = None
            else:
                # identify the man from the chain's company (the links), then grade HIM. First try
                # تمييز المهمل: a bare name whose (تلميذ, شيخ) sandwich the corpus names in full
                # elsewhere is resolved deterministically — «عبد الرحمن» between بشار وسفيان = ابن مهدي.
                name = narrator.name
                # the (تلميذ, شيخ) sandwich is only valid when both neighbours are on the SAME route —
                # a ح seam (i or i+1 begins a new route) gives a false شيخ, so skip تمييز المهمل there.
                same_route = i not in route_starts and (i + 1) not in route_starts
                if muhmal and 0 < i < len(narrators) - 1 and same_route:
                    from app.rijal.muhmal import resolve as _resolve_muhmal
                    name = _resolve_muhmal(name, narrators[i - 1].name, narrators[i + 1].name, muhmal)
                    if name != narrator.name:
                        record["resolved"] = name        # show what the bare name was identified as
                if canon is not None and name == narrator.name:   # still مهمل → company disambiguation
                    # disambiguate by the IMMEDIATE neighbours (the specific شيخ/تلميذ), not the whole
                    # chain: diffuse token-overlap lets a wrong namesake win by coincidence («يونس عن
                    # الزهري» → wrongly يونس بن عبيد). With the immediate company he is resolved or
                    # honestly held — never confidently mis-identified. A ح seam neighbour is on a
                    # different route, so it is NOT used as company.
                    nb: set[str] = set()
                    if i > 0 and i not in route_starts:
                        nb |= _clean_tokens(narrators[i - 1].name)
                    if i < len(narrators) - 1 and (i + 1) not in route_starts:
                        nb |= _clean_tokens(narrators[i + 1].name)
                    ctx = frozenset(nb - _clean_tokens(narrator.name))
                    name = canon.canonical(narrator.name, context=ctx)
                if name == narrator.name and joint[i]:   # still مهمل → the documented شيخ/تلميذ resolver
                    name = joint[i]
                    record["resolved"] = name
                match = rijal.lookup(name)
                # تمييز بالطبقة (by position): when the chain REACHES the Prophet ﷺ, the last human link
                # narrates directly from him, so he is a Companion; if it matches a صحابي, prefer that
                # Companion over a same-name homonym of a later طبقة («عن الأسود عن النبيﷺ» → ابن سريع
                # الصحابي). Gated on reaches_prophet: on a mawqūf/maqṭūʿ chain the terminal is NOT
                # necessarily a Companion (الأسود النخعي التابعي in his own مقطوع), so we must not force
                # صحابي — a genuine Companion there (أبو ذر) is still kept by his natural lookup below.
                if match is not None and reaches_prophet and i == terminal_idx and match.entry.category != "صحابي":
                    sah = [c for c in rijal.candidates(narrator.name) if c.category == "صحابي"]
                    if sah:
                        from app.rijal.index import RijalMatch
                        match = RijalMatch(entry=sah[0], score=1.0, ambiguous=len(sah) > 1,
                                           alternatives=[c.name for c in sah[1:]], grade_agreed=(len(sah) == 1))
                elif match is not None and i < terminal_idx - 1 and match.entry.category == "صحابي":
                    # symmetric, but only DEEP in the chain (≤ terminal−2): a صحابي narrating from a
                    # later narrator is an anachronism → prefer a non-صحابي homonym («جرير» deep →
                    # ابن عبد الحميد الثقة, not البجلي الصحابي). The penultimate link is left alone —
                    # there a younger Companion legitimately narrates from an older one (صحابي عن
                    # صحابي: «ابن عباس عن عمر», «أنس عن عبادة»). max_results=None so a VERY common ism
                    # («عبد الله» — hundreds of homonyms) is not capped to [] here: prominence collapses
                    # the lookup to the prolific bearers (the all-صحابي ابادلة), and the demotion must
                    # still see the later تابعي «عبد الله» to undo it — else the commonest names regress
                    # to a false «صحابي mid-chain».
                    other = [c for c in rijal.candidates(narrator.name, apply_prominence=False,
                                                          max_results=None)
                             if c.category != "صحابي"]
                    if other:
                        from app.rijal.index import RijalMatch
                        cats = {c.category for c in other}
                        match = RijalMatch(entry=other[0], score=1.0, ambiguous=len(other) > 1,
                                           alternatives=[c.name for c in other[1:]], grade_agreed=(len(cats) == 1))
                # A صحابي whose grade rests ONLY on an obscure-Companion dictionary (الإصابة) must not
                # place a Companion DEEP in the chain (≤ terminal−2): his bare ism+father over-matches a
                # later same-named تابعي (محمد بن عبد الله، حارثة بن محمد…) → a false «صحابي mid-chain» that
                # also MASKS the real man's weakness. Drop the match entirely (the card too, not just the
                # verdict): mid-chain he is honestly unknown, not a held ambiguity. He is still identified
                # at the END (terminal / penultimate صحابيٌّ عن صحابيّ) — the whole point of الإصابة.
                if (match is not None and match.entry.category == "صحابي" and i < terminal_idx - 1
                        and from_companion_dictionary(match.entry)):
                    match = None
                # An ambiguous match whose candidates DISAGREE on the grade (عثمان بن أبي شيبة:
                # ثقة vs a متروك namesake) is no confident identification — count him as
                # undetermined (يُتوقَّف), while the card still shows the candidates. But when the
                # tied candidates AGREE (عدي بن حاتم → both صحابي; الليث → both ثقة), the grade is
                # usable, so we keep it.
                usable = match and (not match.ambiguous or match.grade_agreed
                                    or (i == terminal_idx and match.entry.category == "صحابي"))
                matches.append(match if usable else None)
            record["rijal"] = match.to_dict() if match else None
        narrator_dicts.append(record)

    notes: list[str] = []
    if has_tahwil:
        notes.append("فيه تحويل (ح): أكثر من طريق في الإسناد.")
    if has_anana:
        notes.append("في الإسناد عنعنة؛ يُتحقَّق من ثبوت السماع (احتمال التدليس).")
    if mubham_count:
        notes.append("في الإسناد راوٍ مبهمٌ لم يُسمَّ (جهالةُ عينٍ) — سببُ ضعفٍ بذاته، لا نقصٌ في القاعدة.")
    if len(narrators) < 3:
        notes.append("السند قصير؛ يُنظر في اتصاله.")

    if rijal is None:
        assessment = None
        notes.append("تقويم عدالة الرواة وضبطهم يتطلّب قاعدة بيانات الرجال (مرّر RijalIndex لتفعيله).")
    else:
        # total counts only the gradable narrators (the Prophet and المبهمون are excluded above)
        assessment = _chain_assessment(matches, len(matches), mubham=mubham_count)
        notes.append("هذا حكمٌ على الرجال فقط؛ وصحّة الحديث تقتضي أيضًا اتصال السند وانتفاء العلّة والشذوذ.")

    return IsnadAnalysis(
        narrators=narrator_dicts,
        length=len(narrators),
        modes=modes,
        has_tahwil=has_tahwil,
        has_anana=has_anana,
        reaches_prophet=reaches_prophet,
        notes=notes,
        rijal_assessment=assessment,
    )


def continuity(narrators: list[dict], graph) -> dict:
    """Check each تلميذ→شيخ link against the narrator network: is the pair ever recorded
    together? A link never seen is a flag for a possible break (انقطاع) — a structural
    hint from the texts, not a verdict on سماع. ``graph`` is a NarratorGraph."""
    links = []
    for student, teacher in zip(narrators, narrators[1:]):
        if teacher.get("route_start"):
            continue   # ح seam: the route-end and the next route-start aren't a real تلميذ→شيخ link
        weight = graph.link_weight(student["name"], teacher["name"])
        links.append(
            {"from": student["name"], "to": teacher["name"], "count": weight, "seen": weight > 0}
        )
    seen = sum(1 for link in links if link["seen"])
    if not links:
        note = "السند قصير؛ لا حلقات للمقابلة."
    elif seen == len(links):
        note = "كلّ حلقات الإسناد لها رواية معروفة في النصوص."
    else:
        note = (
            f"{len(links) - seen} من {len(links)} حلقة لم تُعرف روايتها في النصوص؛ "
            "يُنظر في الاتصال (قد يكون انقطاعًا أو اختلاف صيغة الاسم)."
        )
    return {"links": links, "seen": seen, "total": len(links), "note": note}


def overall_ruling(analysis: dict, continuity: dict | None = None) -> dict:
    """A single bottom-line «الحكم على الإسناد» that fuses the rijal verdict (by the
    weakest narrator), the اتصال check, and عنعنة.

    It is explicitly a verdict on the *apparent* state of the men and the connection —
    not a full تصحيح, which also needs النظر في العلّة والشذوذ. The narrator ranks come
    from ``app.rijal.grades.RANKS`` (10 = صحابي … 0 = كذاب). ``tone`` (sahih|hasan|daif|
    other) is for display colour. With a small rijal seed many narrators are unknown, so
    a positive verdict is held back to «يُتوقَّف فيه» until a fuller رجال base is loaded."""
    ra = analysis.get("rijal_assessment") or {}
    weakest = ra.get("weakest_rank")
    unknown = ra.get("unknown") or 0
    mubham = ra.get("mubham") or 0
    has_anana = bool(analysis.get("has_anana"))
    broken = bool(
        continuity and continuity.get("total")
        and continuity.get("seen", 0) < continuity["total"]
    )

    # 1) base verdict from the weakest *known* narrator
    if weakest is None:
        grade, tone, reason = (
            "غير محكوم عليه", "other", "لم يُعرف رواة هذا الإسناد في قاعدة الرجال"
        )
    elif weakest <= 1:        # كذاب / متروك
        grade, tone, reason = "ضعيف جدًا", "daif", "في الإسناد راوٍ متروك أو متّهم"
    elif weakest <= 3:        # ضعيف / مجهول
        grade, tone, reason = "ضعيف", "daif", "في الإسناد راوٍ ضعيف أو مجهول"
    elif weakest <= 6:        # لين / مقبول / صدوق له أوهام
        grade, tone, reason = (
            "حسن لغيره", "hasan",
            "في الإسناد مَن لا يُحتجّ بتفرّده؛ يُعتبر به في الشواهد والمتابعات",
        )
    elif weakest <= 8:        # صدوق
        grade, tone, reason = "حسن", "hasan", "أمثل رجاله صدوق؛ حديثه حسن لذاته"
    else:                     # ثقة / صحابي
        grade, tone, reason = "صحيح", "sahih", "رجاله كلّهم ثقات"

    # 2) narrators we couldn't find make a positive verdict non-final (the DB is limited)
    if unknown and tone in ("sahih", "hasan"):
        grade, tone = "يُتوقَّف فيه", "other"
        reason = f"{reason}؛ لكن بقي {unknown} راوٍ لم يُعرف في القاعدة فلا يُجزَم"

    # 2.5) an unnamed narrator (مبهم: «عن رجلٍ») is a real جهالة — a defect in the text, not
    # a gap in our DB. It weakens the chain by itself, whoever the named men are.
    if mubham:
        if "جدًا" not in grade:        # keep «ضعيف جدًا» if a متروك already set it
            grade = "ضعيف"
        tone = "daif"
        reason = f"{reason}؛ وفيه راوٍ مبهمٌ لم يُسمَّ (جهالةُ عينٍ، لا نقصٌ في القاعدة)"

    # 3) the network-continuity check is a weak structural HINT, not a verdict: our graph is
    # built from the same corpus and keyed by canonical name forms, so a missing link is
    # usually just coverage or a different spelling of a name — NOT a real انقطاع. It must
    # never flip an otherwise-sound chain (a صحيح البخاري isnad of ثقات would read «ضعيف»);
    # surface it as a caution to be checked instead.
    if broken:
        reason = (f"{reason}؛ ولم نتأكّد من اتّصال إحدى حلقاته في شبكتنا "
                  "(قد يكون اختلافَ صيغةِ اسمٍ لا انقطاعًا — يُراجَع)")
    elif tone == "sahih" and continuity and continuity.get("total"):
        reason = f"{reason}؛ والإسناد متّصل بحسب الشبكة"

    # 4) عنعنة keeps a sound chain short of a firm تصحيح until السماع is confirmed
    if has_anana and tone == "sahih":
        grade = "صحيح إن ثبت السماع"
        reason = f"{reason}؛ وفيه عنعنة فيُتحقَّق من ثبوت السماع"

    return {
        "grade": grade,
        "tone": tone,
        "reason": reason,
        "disclaimer": (
            "حكمٌ على ظاهر حال الرجال واتصال السند فقط؛ وتمام التصحيح يقتضي النظر في "
            "العلّة والشذوذ. هذه أداة دراسة لا فتوى."
        ),
    }
