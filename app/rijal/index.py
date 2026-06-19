"""A narrator (رجال) lookup: match a name pulled from an isnad to a graded entry.

Arabic narrator names are messy — the same man appears as a bare ism (سفيان), a
nasab (سفيان بن سعيد), or a laqab (الثوري), and isnad extraction leaves honorifics and
spillover. So matching is by the *overlap coefficient* of cleaned token sets
(shared ÷ smaller), and when two equally-good entries tie — the مهمل/مشترك problem,
e.g. سفيان ↦ ابن عيينة vs الثوري — the match is flagged ``ambiguous`` rather than guessed.

The dataset is a small curated seed (``seed.jsonl``, gradings from تقريب التهذيب; the
Companions are عدول by consensus). The full رجال corpus (turath cat-26) can be loaded
on top via ``settings.rijal_path`` — see ``scripts/build_rijal.py``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from app.parsing.normalize import fold_kunya, normalize_for_search
from app.rijal.companions import MAJOR_COMPANIONS, MAJOR_TABIIN
from app.rijal.grades import RANKS, classify

# Honorific ligatures (ﷺ ﵁ …), Quranic/honorific marks, and spelled-out eulogies.
_HONORIFIC_CH = re.compile(r"[﴾-﷿ؐ-ؚۖ-ۭ]")
_HONORIFIC_PHRASE = re.compile(
    r"رضي الله عنه[ام]*|صلى الله عليه وسلم|عليه السلام|رحمه الله|رضوان الله عليه|"
    # honorific descriptors that aren't part of a name — «عائشة زوج النبي ﷺ» / «… أم
    # المؤمنين» would otherwise stay unmatched (and ungraded) and split into many nodes.
    r"أم المؤمنين|أمير المؤمنين|"
    r"(?:زوج|زوجة|أم|بنت|عم|عمة|خال|خالة|خادم|مولى|مولاة|صاحب|مؤذن|حب|رضيع)\s+(?:النبي|رسول الله)"
)
# Tokens that are transmission verbs / spillover / non-discriminating connectors, never
# an identifying part of a name. «بن/ابن» are dropped so «خالد بن عمر» and «عمر بن الخطاب»
# don't look alike merely through the shared «بن».
_STOP = {normalize_for_search(w) for w in (
    "قال قالت يقول سمع سمعت يحدث أنه حدثنا حدثني أخبرنا أخبرني عن نا ثنا يعني المنبر بن ابن"
).split()}
# A query that, cleaned, is *only* one of these identifies no one — a bare kunya particle
# (أبو/أبي/أبا), «أم», «عبد», or a 3rd-person KINSHIP possessive (أبيه/جده/أمه…). We refuse to
# match rather than guess: «أبي» would else hit «عائشة بنت أبي بكر» through «بنت أبي بكر», «عبد»
# any «عبد الله», and «أبيه» any entry that mentions «… واسم أبيه فلان».
_NON_IDENTIFYING = {normalize_for_search(w) for w in (
    "أبو أبي أبا أم عبد أبيه أمه جده جدته أخيه أخته عمه عمته خاله خالته ابنه بنته"
).split()}

# A chain cites a name with or without its definite article — «ليث»/«الليث», «حسن»/«الحسن», «أسود»/
# «الأسود». We recover this WITHOUT broadening: an entry «الليث …» also gets an «ال»-stripped matching
# FORM «ليث …» (so a bare «ليث» finds it), but the query is NOT folded — a citation that KEEPS the
# article («الحسن») stays the specific man and does not collapse into the «حسن» pool (which is what
# inflated «مشترك»). Never the divine names («عبد الله»/«عبد الرحمن»), and only a ≥3-char stem.
_AL_KEEP = {normalize_for_search(w) for w in ("الله", "الرحمن", "الرحيم", "اللهم", "الإله")}


def _al_variant(seq: list[str]) -> list[str] | None:
    """The token sequence with «ال» stripped from the LEADING ism (an extra matching form so «ليث» finds
    «الليث»), or ``None`` when the lead carries no foldable article. Only the leading token — a citation
    drops the article on the ism, nisbas keep theirs — never a divine name, ≥3-char stem."""
    if seq and seq[0].startswith("ال") and len(seq[0]) >= 5 and seq[0] not in _AL_KEEP:
        return [seq[0][2:], *seq[1:]]
    return None


def _al_strip_query(name: str) -> str | None:
    """A query «المعتمر بن سليمان» whose leading ism carries «ال» but the base entry has none
    («معتمر بن سليمان» في التقريب). Returns the name with «ال» stripped from the leading ism — but ONLY
    when the query is MULTI-token, so the nasab disambiguates and a bare «الحسن» is NEVER broadened into
    the «حسن» pool (the #189/#190 hazard). Used as a fallback in :meth:`lookup` only when the literal
    query MISSES, so it can never regress a working match — it only recovers an uncovered narrator."""
    seq = _clean_seq(name)
    if len(seq) >= 2 and (av := _al_variant(seq)) is not None:
        return " ".join(av)
    return None


def _clean_seq(name: str) -> list[str]:
    """Folded name tokens **in order**, honorifics/connectors dropped. A token repeated NON-adjacently
    (a distant ancestor) is dropped, but an ADJACENT repeat is KEPT: «معاذ بن معاذ» (ism = father's
    name) is a real two-token name (معاذ بن معاذ العنبري القاضي), NOT the bare «معاذ» that would match
    every معاذ بن فلان and make a famous narrator «مشترك» among twenty men.

    Kunya cases are unified (أبو/أبا/أبي → أبو) before «بن» is dropped, so «أبي موسى»
    matches «أبو موسى»; «أبي بن …» stays أُبَيّ (a name, not a kunya). (The «ال» variant is a separate
    per-entry matching form, see `_al_variant`, not a fold here.)"""
    text = _HONORIFIC_PHRASE.sub(" ", _HONORIFIC_CH.sub(" ", name or ""))
    seen: set[str] = set()
    out: list[str] = []
    for t in fold_kunya(normalize_for_search(text).split()):
        if t and t not in _STOP and (t not in seen or out[-1] == t):
            seen.add(t)
            out.append(t)
    return out


def _clean_tokens(name: str) -> set[str]:
    return set(_clean_seq(name))


# Curated, closed anchor SEQUENCES (folded once, IN ORDER): a high-status narrator whose رجال entry
# carries NO grade — or is mis-graded صحابي for a known تابعي — is anchored to the documentary verdict.
# A form must IDENTIFY THE SUBJECT (its leading run, or his own kunya), never an ancestor buried in his
# nasab. See app/rijal/companions.py.
_COMPANION_SEQS = [s for s in (_clean_seq(c) for c in MAJOR_COMPANIONS) if len(s) >= 2]
_TABII_SEQS = [s for s in (_clean_seq(c) for c in MAJOR_TABIIN) if len(s) >= 2]


def _contiguous(sub: list[str], full: list[str]) -> bool:
    """Does ``sub`` occur as a contiguous run anywhere in ``full``?"""
    n = len(sub)
    return n > 0 and any(full[i:i + n] == sub for i in range(len(full) - n + 1))


def _ordered_subseq(sub: list[str], full: list[str]) -> bool:
    """Do ``sub``'s tokens all appear in ``full`` IN ORDER (a kunya/extra token may sit between them)?"""
    it = iter(full)
    return all(tok in it for tok in sub)


def _form_identifies(name_seq: list[str], forms: list[list[str]]) -> bool:
    """Does a curated form name the SUBJECT of the name — not an ancestor buried in his nasab?
    An ism-led form matches when its **ism AND immediate father** are the name's leading two tokens
    and the rest (the nisba) follows IN ORDER — so «عامر بن شراحيل الشعبي» identifies «عامر بن شراحيل
    أبو عمرو الشعبي» (the kunya is skipped) but «الحسن بن علي بن أبي طالب» (father علي) does NOT identify
    his تابعي son «الحسن بن الحسن بن علي …» (father الحسن — the form names the GRANDFATHER's line, i.e.
    an ancestor). A kunya-led form matches the subject's OWN kunya (a contiguous run «أبو هريرة الدوسي»)."""
    for f in forms:
        if f[0] in _KUNYA_PARTICLES:
            if _contiguous(f, name_seq):
                return True
        elif (name_seq[:1] == f[:1]                                    # same ism (leading)
              and (len(f) < 2 or (len(name_seq) >= 2 and name_seq[1] == f[1]))   # same immediate father
              and _ordered_subseq(f, name_seq)):                       # the nisba etc. follow in order
            return True
    return False


def _anchor_grade(name: str) -> tuple[str, int] | None:
    """If the name's SUBJECT is a major Companion → («صحابي», 10); a major تابعي ثقة → («ثقة», 9); else
    ``None``. Used to recover an ungraded entry AND to correct a known تابعي mis-graded صحابي."""
    seq = _clean_seq(name)
    if _form_identifies(seq, _COMPANION_SEQS):
        return "صحابي", RANKS["صحابي"]
    if _form_identifies(seq, _TABII_SEQS):
        return "ثقة", RANKS["ثقة"]
    return None


# Kunya particles after folding (أبو/أبا/أبي → ابو, أم → ام). A form that *starts* with
# one is a teknonym — «أبو بكر», «أم سلمة», «أبو عبد الله» — and must be matched
# reverse-only (the chain has to cite the man BY it), never glued onto a longer, different
# name that merely contains it: «أبو بكر بن أبي شيبة» (a حافظ) is not «أبو بكر» the Companion.
_KUNYA_PARTICLES = {normalize_for_search("أبو"), normalize_for_search("أم")}
_GRAVE = {"كذاب", "وضاع", "متروك", "متهم"}   # the gravest verdicts — must not shadow a sound namesake


def _is_kunya_form(seq: list[str]) -> bool:
    """True if ``seq`` is a *bare* teknonym — «أبو/أم + one name», exactly 2 tokens —
    matched reverse-only. A longer name that merely starts with a kunya is NOT one: it has
    enough tokens to identify a man on its own («أبو الزناد عبد الله بن ذكوان»)."""
    return len(seq) == 2 and seq[0] in _KUNYA_PARTICLES


def _is_nasab_ref(name: str) -> bool:
    """True when the citation is a bare «ابن …» / «ابن أبي …» — a DESCENDANT reference, not a kunya.
    «ابن أبي مليكة» is عبد الله بن عبيد الله بن أبي مليكة (the تابعي known by that nasab), not his
    grandfather أبو مليكة. So the teknonym (reverse-kunya) match is suppressed for it: otherwise the
    bare «ابن أبي X» folds to the kunya «أبو X» (ابن dropped, أبي→أبو) and grabs the wrong — often
    صحابي — ancestor (a major source of false «صحابي mid-chain» flags: ابن أبي مليكة، ابن أبي ذئب…)."""
    toks = normalize_for_search(name).split()
    return bool(toks) and toks[0] in ("ابن", "بن")


# Shuhra-by-(distant-)ancestor: a man universally cited by an ANCESTOR's name with «ابن», where that
# ancestor sits DEEP in his nasab (grandfather or beyond). The token matcher drops «ابن» and reads
# «ابن جريج» as a bare «جريج», a non-leading partial of EVERY man carrying جريج (his father, the
# literal «X بن جريج» sons…), so he ties «مشترك» and never resolves. This CLOSED, documentary map (an
# established رجال shuhra is not a guess) redirects the bare shuhra to the man's full canonical name,
# so the ordinary lookup resolves him uniquely and his grade/company flow. Keys are folded token
# tuples; the match is EXACT on the bare shuhra only — «ابن جريج المكي», or a different «X بن جريج»
# son, has a different token tuple and falls through to normal matching. A *direct* «ابن X» (ابن
# سيرين = محمد بن سيرين, whose FATHER is سيرين) already resolves by the literal-son partial → not here.
_SHUHRA: dict[tuple[str, ...], str] = {
    tuple(t for t in (normalize_for_search(w) for w in form.split()) if t): canonical
    for form, canonical in {
        "ابن جريج": "عبد الملك بن عبد العزيز بن جريج",                        # جدّه جُرَيج · ثقة فقيه · مكّي
        "ابن أبي ذئب": "محمد بن عبد الرحمن بن المغيرة بن الحارث بن أبي ذئب",   # ثقة · المدني (لا خالُه «الحارث»)
        "ابن أبي مليكة": "عبد الله بن عبيد الله بن عبد الله بن أبي مليكة",      # القاضي · ثقة (لا ذرّيّةٌ ضعيفة)
        "ابن أبي هلال": "سعيد بن أبي هلال الليثي",                             # صدوق (لا الكذّاب يعقوب بن الوليد)
        "ابن أبي عمر": "محمد بن يحيى بن أبي عمر العدني",                       # شيخ مسلم · ثقة (جدّه أبو عمر)
        "ابن أبي عمر المكي": "محمد بن يحيى بن أبي عمر العدني",                  # …with the nisba (مسلم: not a صحابي)
        "ابن أبي خلف": "محمد بن أحمد بن أبي خلف القطيعي",                       # شيخ مسلم · ثقة (لا كذّابُ «أبي خلف»)
        # NB «ابن وهب» NOT redirected: a bare صحابيّ «عبد الله بن وهب» contains-matches any «عبد الله بن
        # وهب …» target and wins, so a redirect would grade it صحابيّ — left held «مشترك» (harmless floor).
        "أبو سعيد الأشج": "عبد الله بن سعيد الأشج",                            # الكنديّ الكوفيّ · ثقة · شيخ الجماعة
        "أبو معاوية": "محمد بن خازم الضرير",                                   # صاحبُ الأعمش · ثقة (لا البجليُّ النادر)
        "أبو نعيم": "الفضل بن دكين",                                          # الكوفيّ · ثقة · شيخ البخاري (لا المتأخّر)
    }.items()
}


# Famous-Companion kunya: a chain that cites a bare kunya «أبو هريرة» means the Companion, but the base
# ALSO holds obscure late namesakes carrying the same kunya (محمد بن أيوب الواسطي صدوق، محمد بن فراس
# الضبعي…) + a duplicate of the Companion himself («أبو هريرة الدوسي» beside «عبد الرحمن بن صخر الدوسي»),
# so the bare kunya ties «مشترك» and the matcher may even pick the obscure namesake (wrong verdict, not
# just an honest hold). This CLOSED, documentary map (أبو هريرة = عبد الرحمن بن صخر الدوسي is established
# رجال, not a guess) redirects the bare kunya to the Companion's full canonical ism, so the ordinary
# lookup resolves him uniquely (صحابي) and his grade flows. Keys are kunya-FOLDED token tuples (via
# `_clean_seq`, so أبو/أبا/أبي هريرة all match), EXACT on the bare kunya only — «أبو هريرة الدوسي» /
# «الواسطي» (with a nisba) folds to a longer tuple and falls through to normal matching.
_KUNYA_COMPANION: dict[tuple[str, ...], str] = {
    tuple(_clean_seq(form)): canonical
    for form, canonical in {
        "أبو هريرة": "عبد الرحمن بن صخر الدوسي",   # ثقة الصحابة · المُكثِر · ت57
        "أبو ذر": "جندب بن جنادة الغفاري",          # الصحابيّ · ت32 (لا عمر بن ذرّ الكوفيّ، ولا الهرويّ)
        "أبو الدرداء": "عويمر بن زيد الأنصاري",     # الصحابيّ عويمر · ت32 (لا ابن منيب المروزيّ المتأخّر)
    }.items()
}


def _resolve_shuhra(name: str) -> str:
    """Redirect a bare shuhra-by-ancestor citation («ابن جريج») or a bare famous-Companion kunya
    («أبو هريرة») to the man's full canonical name; otherwise return ``name`` unchanged."""
    key = tuple(t for t in (normalize_for_search(w) for w in name.split()) if t)
    if key in _SHUHRA:
        return _SHUHRA[key]
    return _KUNYA_COMPANION.get(tuple(_clean_seq(name)), name)


def _is_flipped_alias(alias: str, name_ism: str | None) -> bool:
    """True when ``alias`` is a person-name whose ism differs from the entry's own — a «flipped» or
    garbled alternate form that must NOT become a matchable identity.

    محمد بن سعيد المصلوب «قلبوا اسمه على وجوه» → a flipped form «سعد بن سعيد» was extracted as an alias;
    as an exact 2-token containment it then OUTRANKS the real سعد بن سعيد الأنصاري (a Muslim narrator)
    and stamps the كذاب verdict on a sound chain. Most such aliases are extraction noise (ضبط notes,
    truncated fragments, stray verdict words). A kunya alias (أبو/أم …) is exempt — it is matched
    reverse-only and is a legitimate way to cite the man."""
    a = _clean_seq(alias)
    return bool(len(a) >= 2 and a[0] not in _KUNYA_PARTICLES and name_ism and a[0] != name_ism)


def _order_ok(q_seq: list[str], f_seq: list[str], shared: set[str]) -> bool:
    """True if the shared tokens appear in the same relative order in both — so a query
    «يزيد بن جابر» does NOT match a form «جابر بن يزيد» (a different man)."""
    return [t for t in q_seq if t in shared] == [t for t in f_seq if t in shared]


def _score_entry(
    query_seq: list[str], query: set[str], seqs: list[list[str]], kunya_seqs: list[list[str]],
    *, teknonym: bool = True, nasab_ref: bool = False,
) -> tuple[int, tuple[int, bool, int] | None]:
    """Score one entry against the query.

    Returns ``(specificity, best_partial)``. ``specificity > 0`` means an entry form is fully
    inside the query (containment — the entry's name appears in the cited name). ``best_partial
    = (cover, is_prefix, form_len)`` means the cited name is a partial of a form (query ⊆ form);
    ``is_prefix`` is True when the query is the *leading run* of that form — its ism+nasab —
    which marks the natural identity: «عدي بن حاتم» is عدي بن حاتم الطائي (prefix), not عدي بن
    الفضل … أبو حاتم (where حاتم only shows up later, inside a kunya). Teknonym forms
    (``kunya_seqs``) match reverse-only and only when the query is itself a kunya.

    ``nasab_ref`` (a «ابن X» citation) means X is a FATHER, so a leading (ism-position) match is
    wrong: «ابن عمر» is the son عبد الله بن عمر, never عمر بن الخطاب the eponym (nor any of the 134
    men *named* عمر). Such prefix partials are dropped — X must sit non-leading (as a father)."""
    specificity = 0
    best: tuple[int, bool, int] | None = None
    qlen = len(query_seq)

    def offer(seq: list[str]) -> None:
        nonlocal best
        is_prefix = seq[:qlen] == query_seq
        if nasab_ref and is_prefix:
            return    # «ابن عمر» — عمر is the FATHER (non-leading); never the ism (the eponym)
        cand = (len(query), is_prefix, len(seq))   # (cover, is_prefix, form_len)
        if best is None or (cand[0], cand[1], -cand[2]) > (best[0], best[1], -best[2]):
            best = cand

    for seq in seqs:
        form = set(seq)
        # a bare single-token form (an ism like «عمر») can't confidently identify a more
        # fully-named query («خالد بن عمر») — only an exact bare-name query may match it.
        if len(form) == 1 and len(query) > 1:
            continue
        shared = query & form
        if not shared or not _order_ok(query_seq, seq, shared):
            continue
        if len(shared) == len(form):               # form ⊆ query → entry's name is in the query …
            if query_seq[:len(seq)] == seq and not nasab_ref:   # … as its LEADING run (the cited man).
                specificity = max(specificity, len(form))   # For «ابن X», X is a FATHER, so a bare-ism
                # entry «عمر» must NOT lead-match «ابن عمر» (the eponym, nor any of the 134 men NAMED
                # عمر) — the son «عبد الله بن عمر بن الخطاب» matches via the partial branch (X non-leading)
                # instead. (Buried ancestors were already excluded — only the LEADING run sets specificity.)
        elif len(shared) == len(query):            # query ⊆ form → cited name is a partial
            offer(seq)
        # else: neither contains the other → coincidental shared token(s), not a match
    # teknonyms identify a man only when the chain cites him BY the kunya: the query must
    # itself be a kunya («أبو …»/«أم …») AND lie within the form. A bare ism «معمر» is NOT the
    # man whose kunya is «أبو معمر»; «حبيب بن أبي ثابت» is not the kunya «أبو ثابت». Suppressed
    # (``teknonym=False``) for a «ابن أبي …» citation: «ابن أبي مليكة» is the DESCENDANT (عبد الله بن
    # عبيد الله), never the grandfather whose kunya is «أبو مليكة» — see `_is_nasab_ref`.
    if teknonym and query_seq and query_seq[0] in _KUNYA_PARTICLES:
        for kseq in kunya_seqs:                      # only query ⊆ kunya (reverse)
            if query <= set(kseq) and _order_ok(query_seq, kseq, query):
                offer(kseq)
    return specificity, best


@dataclass(slots=True)
class RijalEntry:
    name: str
    aliases: list[str]
    kunya: str | None
    grade_text: str
    category: str
    rank: int | None
    death_year: int | None
    source: str | None
    opinions: list[dict] | None = None   # [{source, grade}] — the «double opinion» (ابن حجر/الذهبي)
    appraisals: list[dict] | None = None  # [{critic, verdict}] — the NAMED أقوال الأئمة (from prose sources)


@dataclass(slots=True)
class RijalMatch:
    entry: RijalEntry
    score: float
    ambiguous: bool
    alternatives: list[str]
    grade_agreed: bool = True   # do all the tied candidates share one grade? (then it's usable)

    def to_dict(self) -> dict:
        return {
            "name": self.entry.name,
            "kunya": self.entry.kunya,
            "grade": self.entry.category,
            "rank": self.entry.rank,
            "verdict": self.entry.grade_text,
            "death_year": self.entry.death_year,
            "source": self.entry.source,
            "match_score": self.score,
            "ambiguous": self.ambiguous,
            "grade_agreed": self.grade_agreed,
            "alternatives": self.alternatives,
            "opinions": self.entry.opinions,
            "appraisals": self.entry.appraisals,
            # مختلف فيه: the critics' opinions (تقريب/الكاشف…) span ≥2 distinct grades — surfaced on the
            # card and counted conservatively in the isnad verdict (the weakest opinion).
            "disputed": len({o.get("grade") for o in (self.entry.opinions or []) if o.get("grade")}) >= 2,
        }


# Companion dictionaries (الإصابة and, later, its siblings) catalogue the obscure صحابة who barely
# narrate. Their worth is identifying a Companion at the chain's END; DEEP in a chain a bare ism+father
# from one of them over-matches a later same-named تابعي (محمد بن عبد الله، حارثة بن محمد…). So a صحابي
# whose grade rests ONLY on such a source is not used to place a Companion mid-chain (see analyze_isnad).
_COMPANION_DICTIONARIES = ("الإصابة",)


def from_companion_dictionary(entry: RijalEntry) -> bool:
    """True if the entry's grade comes from an obscure-Companion dictionary (الإصابة …)."""
    return any(s in (entry.source or "") for s in _COMPANION_DICTIONARIES)


# Add-only COVERAGE dictionaries (الإصابة صحابة · الثقات ثقات): men OUTSIDE the Six Books, who barely
# narrate there. They pull a genuinely-cited obscure man out of «مجهول», but they must NOT shadow a real
# narrator for a BARE/kunya citation — «أبي هريرة» is the Companion الدوسي, not an obscure محمد who merely
# shares the kunya. So a coverage man competes only when there is no non-coverage candidate (see _lookup).
_COVERAGE_SOURCES = ("الإصابة", "الثقات")


def from_coverage_source(entry: RijalEntry) -> bool:
    """True if the entry exists ONLY because an add-only coverage dictionary (الإصابة/الثقات) added it."""
    return any(s in (entry.source or "") for s in _COVERAGE_SOURCES)


def _prefer_non_coverage(group: list[RijalEntry]) -> list[RijalEntry]:
    """Drop coverage-only men from a tied candidate group when a real (non-coverage) narrator is present —
    so an obscure الإصابة/الثقات namesake never makes a famous narrator «مشترك». Kept only when EVERY
    candidate is coverage (a genuinely non-Six-Books citation, where the obscure man may be the referent)."""
    real = [e for e in group if not from_coverage_source(e)]
    return real if real else group


# The Arabic alphabet, in order — for the «تصفّح الرواة» browse index, where each narrator is
# filed under his name's first significant letter. Hamza forms fold to ا and a leading «ال»
# (the definite article) is skipped (see ``_browse_letter``), so «إبراهيم» files under ا and
# «الزهري» under ز, matching how a reader looks a name up.
_ALPHABET = "ابتثجحخدذرزسشصضطظعغفقكلمنهوي"


def _browse_letter(name: str) -> str:
    """The alphabet letter a narrator's name is filed under (first letter, folded), or «#»."""
    folded = normalize_for_search(name).strip()
    if folded.startswith("ال") and len(folded) > 3:   # skip the definite article «ال…»
        folded = folded[2:]
    for ch in folded:
        if ch in _ALPHABET:
            return ch
    return "#"


class RijalIndex:
    """In-memory narrator lookup (linear; the corpus of named narrators is small)."""

    def __init__(self, entries: Iterable[dict] | None = None) -> None:
        self._entries: list[RijalEntry] = []
        self._form_seqs: list[list[list[str]]] = []   # name + alias token-seqs (full matching)
        self._kunya_seqs: list[list[list[str]]] = []   # reverse-only forms: teknonyms + kunya
        self._cache: dict[tuple[str, float], "RijalMatch | None"] = {}  # memoise lookups
        self._cand_cache: dict[tuple[str, int | None, bool], list[RijalEntry]] = {}  # memoise candidates
        self._prominence: dict[str, int] = {}          # name → corpus narration frequency (set externally)
        self._browse: list[dict] | None = None         # cached «تصفّح الرواة» browse rows
        if entries:
            self.add(entries)

    def set_prominence(self, prominence: dict[str, int]) -> None:
        """Supply each canonical name's corpus narration frequency (from the narrator graph) — the
        PROMINENCE prior used to break a tie toward the prolific narrator. Clears the lookup cache."""
        self._prominence = prominence or {}
        self._cache.clear()
        self._cand_cache.clear()      # prominence changes which candidates survive → drop the memo

    _PROM_RATIO = 4   # keep a tied candidate only if ≥ 1/RATIO as prolific as the most prolific one

    def _prefer_prominent(self, group: list["RijalEntry"]) -> list["RijalEntry"]:
        """Among tied candidates, prefer the prolific narrator (corpus-frequency prior): «ابن عمر» is the
        much-narrated عبد الله بن عمر, not an obscure same-father man; «أبي هريرة» is الدوسي. Drops a
        candidate FAR less prominent than the top, but KEEPS comparably-prominent rivals (سفيان عيينة/
        الثوري → both kept → honest «مشترك»). No data, or all-zero → unchanged."""
        if len(group) <= 1 or not self._prominence:
            return group
        ranked = sorted(group, key=lambda e: -self._prominence.get(e.name, 0))
        top = self._prominence.get(ranked[0].name, 0)
        if top <= 0:
            return group
        return [e for e in ranked if self._prominence.get(e.name, 0) * self._PROM_RATIO >= top]

    def _keep_trust_over_grave(self, kept: list["RijalEntry"],
                               original: list["RijalEntry"]) -> list["RijalEntry"]:
        """The coverage / prominence filters must NEVER leave a grave (كذاب/متروك/متهم) as the SOLE
        survivor when a non-grave namesake was equally cited — else a bare name confidently sinks a
        sound chain (the obscure trustworthy man dropped, the prolific متروك kept: «محمد بن الزبير» →
        the متروك الحنظلي, dropping the ثقة مولى المعيطيين from الثقات). Add the best non-grave back so
        the match is HELD (ambiguous, grades disagree → يُتوقَّف)."""
        if kept and all(e.category in _GRAVE for e in kept):
            trust = [e for e in original if e.category not in _GRAVE]
            if trust:
                return kept + trust[:1]
        return kept

    def add(self, entries: Iterable[dict]) -> int:
        n = 0
        for raw in entries:
            category, rank = classify(raw.get("grade") or "")
            # A KNOWN major تابعي can NEVER be a «صحابي». When his grade is mis-extracted as صحابي — a
            # Companion-description/طبقة phrase leaking, often onto a truncated entry «عامر … الشعبي أحد»
            # — correct it to ثقة, else that bad entry shadows the real man and reads «صحابي» mid-chain
            # (an S flag: الشعبي/عبيد الله بن عبد الله بن عتبة/قيس بن أبي حازم). The curated _TABII_FORMS
            # are تابعون by consensus, so this is documentary; a name that ALSO matches a Companion form
            # (anchor → صحابي) is left untouched, so a real Companion keeps his grade.
            if category == "صحابي":
                anchor = _anchor_grade(raw["name"])
                if anchor and anchor[0] == "ثقة":
                    category, rank = anchor
            # A Companion's bio («أحد العشرة أسلم قديمًا …») sometimes leaks into his NAME, not the grade,
            # so a major صحابي (عبد الرحمن بن عوف) is mis-graded «مجهول» → a chain through him reads «راوٍ
            # مجهول». Recover صحابي from his own name when the grade is silent (only ever PROMOTES).
            if category == "غير معروف":
                # A high-status narrator must not read «مجهول» just because his grade wasn't extracted.
                # (1) A curated, CLOSED anchor — a major Companion (→صحابي) or a major تابعي ثقة (→ثقة);
                # these are the well-known referents, documentary not guessed (app/rijal/companions.py).
                # (2) Else recover a POSITIVE grade that leaked into his NAME (عبد الرحمن بن عوف «أحد
                # العشرة …») — never a negative one, which could sink a sound chain on a coincidental word.
                anchor = _anchor_grade(raw["name"])
                if anchor:
                    category, rank = anchor
                else:
                    name_cat, name_rank = classify(raw["name"])
                    if name_cat in ("صحابي", "ثقة", "صدوق", "مقبول"):
                        category, rank = name_cat, name_rank
            entry = RijalEntry(
                name=raw["name"],
                aliases=list(raw.get("aliases") or []),
                kunya=raw.get("kunya"),
                grade_text=raw.get("grade") or "",
                category=category,
                rank=rank,
                death_year=raw.get("death_year"),
                source=raw.get("source"),
                opinions=raw.get("opinions"),
                appraisals=raw.get("appraisals"),
            )
            # Non-teknonym names/aliases match by containment either way; teknonyms (a
            # name/alias/kunya leading with أبو/أم) are kept apart and matched reverse-only:
            # a chain may cite a man BY his kunya (أبو هريرة), but a common kunya («أبو بكر»)
            # must NOT glue onto a fuller, different name that merely contains it.
            # Drop «flipped-name» aliases (a different ism — an extraction/confusion artifact) so a
            # man's garbled alternate form can't out-rank, and stamp its grade onto, a real namesake.
            name_ism = next(iter(_clean_seq(entry.name)), None)
            aliases = [a for a in entry.aliases if not _is_flipped_alias(a, name_ism)]
            forms = [s for s in (_clean_seq(f) for f in (entry.name, *aliases)) if s]
            forms += [av for s in list(forms) if (av := _al_variant(s))]   # «الليث» also matchable as «ليث»
            kunya_field = _clean_seq(entry.kunya) if entry.kunya else None
            reverse_only: list[list[str]] = []
            seen_ro: set[tuple[str, ...]] = set()
            for seq in [s for s in forms if _is_kunya_form(s)] + ([kunya_field] if kunya_field else []):
                if seq and tuple(seq) not in seen_ro:
                    seen_ro.add(tuple(seq))
                    reverse_only.append(seq)
            self._entries.append(entry)
            self._form_seqs.append([s for s in forms if not _is_kunya_form(s)])
            self._kunya_seqs.append(reverse_only)
            n += 1
        self._cache.clear()        # entries changed → drop memoised lookups
        self._cand_cache.clear()   # …and memoised candidate sets
        self._browse = None        # …and the browse index
        return n

    def count(self) -> int:
        return len(self._entries)

    def browse_rows(self) -> list[dict]:
        """All narrators as lightweight, alphabetically-sorted rows for the «تصفّح الرواة» index:
        ``{name, grade, death_year, kunya, letter}``. De-duplicated by exact name (a same-man
        dedup gap must not double a row) and cached (rebuilt on ``add``). This is the data behind
        browsing the رجال *without* a search — pick a letter or a درجة and scroll."""
        if self._browse is None:
            seen: dict[str, dict] = {}
            for e in self._entries:
                if e.name in seen:
                    continue
                seen[e.name] = {"name": e.name, "grade": e.category, "death_year": e.death_year,
                                "kunya": e.kunya, "letter": _browse_letter(e.name)}
            self._browse = sorted(seen.values(), key=lambda r: normalize_for_search(r["name"]))
        return self._browse

    def lookup(self, name: str, *, min_overlap: float = 0.6) -> RijalMatch | None:
        """Best narrator match, or ``None`` (memoised — the same name recurs across chains)."""
        key = (name, min_overlap)
        if key not in self._cache:
            m = self._lookup(name, min_overlap=min_overlap)
            if m is None and (alt := _al_strip_query(name)) is not None:
                m = self._lookup(alt, min_overlap=min_overlap)   # «المعتمر بن سليمان» → «معتمر بن سليمان»
            self._cache[key] = m
        return self._cache[key]

    def _lookup(self, name: str, *, min_overlap: float = 0.6) -> RijalMatch | None:
        """Best narrator match, or ``None``.

        A match must be a **containment**: either the entry's name is fully inside the query
        (query «عمر بن الخطاب علي» ⊇ «عمر بن الخطاب») — the most specific such name wins, so a
        man stays distinct from his longer-named son «عبد الله بن عمر» — or the cited name is a
        partial of the entry («الزهري» ⊆ «محمد بن مسلم … الزهري»). Names that merely *share* a
        common token (محمد بن عبد الله بن نمير vs عبد الله بن عمر) are NOT a match — that
        coincidence is what made reliable men read as weak namesakes. Equally-good rivals
        (سفيان ↦ ابن عيينة/الثوري) are flagged ambiguous rather than guessed.
        """
        name = _resolve_shuhra(name)          # «ابن جريج» → عبد الملك بن عبد العزيز بن جريج
        query_seq = _clean_seq(name)
        query = set(query_seq)
        if not query:
            return None
        if len(query) == 1 and query_seq[0] in _NON_IDENTIFYING:
            return None     # a bare kinship/connector particle — identifies no one
        teknonym = not _is_nasab_ref(name)   # «ابن أبي X» is a descendant, not the kunya «أبو X»

        contained: list[tuple[int, RijalEntry]] = []                  # (specificity, entry)
        partial: list[tuple[int, bool, int, RijalEntry]] = []         # (cover, is_prefix, len, entry)
        for entry, seqs, kunya_seqs in zip(self._entries, self._form_seqs, self._kunya_seqs):
            specificity, best = _score_entry(
                query_seq, query, seqs, kunya_seqs, teknonym=teknonym, nasab_ref=not teknonym)
            if specificity:
                contained.append((specificity, entry))
            elif best:
                partial.append((best[0], best[1], best[2], entry))

        if contained:
            contained.sort(key=lambda pair: -pair[0])
            top = contained[0][0]
            tied = [e for s, e in contained if s == top]
            group = self._keep_trust_over_grave(
                self._prefer_prominent(_prefer_non_coverage(tied)), tied)
            best_e = group[0]
            extra = [e for e in group if e.name != best_e.name]
            # A SHORT grave exact-match must not confidently stamp a sound chain when a FULLER,
            # better-graded namesake also fits the bare citation: «إسحاق بن عمر» [متروك] beside the
            # fuller «إسحاق بن عمر بن سليط الهذلي» [ثقة] → hold (ambiguous) so the grade-agreement gate
            # never grades the chain متروك. A lone grave (أصبغ بن نباتة — no namesake) still resolves.
            if best_e.category in _GRAVE:
                extra += [e for _c, _p, _ln, e in partial if e.category not in _GRAVE]
            alternatives = [e.name for e in extra]
            agreed = all(e.category == best_e.category for e in (best_e, *extra))
            return RijalMatch(best_e, 1.0, bool(alternatives), alternatives[:3], grade_agreed=agreed)

        if partial:
            # cover the query most; then prefer a *prefix* form (the cited ism+nasab) over one
            # where the shared tokens only coincide deeper in the name; then the shortest.
            partial.sort(key=lambda t: (-t[0], not t[1], t[2]))
            top_cov, top_pref = partial[0][0], partial[0][1]
            # ambiguous only among equally-good readings (same cover AND prefix-ness): «عدي بن
            # حاتم» → عدي بن حاتم الطائي (the only prefix) is decisive, while «سعيد» → المسيب/جبير
            # (both prefixes) stays مشترك. When the tied readings AGREE on the grade (الليث بن سعد
            # of الكاشف vs تقريب — same man, both ثقة), that grade is still usable.
            tied = [e for cov, pref, ln, e in partial if cov == top_cov and pref == top_pref]
            group = self._keep_trust_over_grave(
                self._prefer_prominent(_prefer_non_coverage(tied)), tied)
            best_e = group[0]
            alternatives = [e.name for e in group if e.name != best_e.name]
            agreed = all(e.category == best_e.category for e in group)
            return RijalMatch(best_e, 1.0, bool(alternatives), alternatives[:3], grade_agreed=agreed)

        return None

    def candidates(self, name: str, *, max_results: int | None = 40,
                   apply_prominence: bool = True) -> list[RijalEntry]:
        """The distinct known men who could be ``name`` — the homonym set for context-based
        تمييز المهمل («the chain before the name»).

        Unlike :meth:`lookup`, which collapses to one best answer, this returns *all* the
        real namesakes — the most-specific contained name(s) AND every best-covering partial
        (fuller-named) homonym — so the chain's company can choose between them, e.g. «محمد
        بن بشر» [متروك] vs «محمد بن بشر العبدي» [ثقة].

        ``max_results`` caps the set: with the default 40, a bare ism with dozens of bearers is
        too generic for a *chain* to resolve, so we return nothing then (the caller holds). Pass
        ``max_results=None`` to get the **full** homonym list regardless — for the disambiguation
        UI, where showing all 134 «عمر» is exactly the point (تمييز المهمل left to the user).
        """
        ckey = (name, max_results, apply_prominence)   # memoised — the joint resolver's pre-pass calls
        cached = self._cand_cache.get(ckey)            # this for every link across tens of thousands of chains
        if cached is not None:
            return cached
        name = _resolve_shuhra(name)          # «ابن جريج» → عبد الملك بن عبد العزيز بن جريج
        query_seq = _clean_seq(name)
        query = set(query_seq)
        if not query or (len(query) == 1 and query_seq[0] in _NON_IDENTIFYING):
            self._cand_cache[ckey] = []
            return []
        teknonym = not _is_nasab_ref(name)   # «ابن أبي X» is a descendant, not the kunya «أبو X»
        contained: list[tuple[int, RijalEntry]] = []
        partial: list[tuple[int, bool, RijalEntry]] = []
        for entry, seqs, kunya_seqs in zip(self._entries, self._form_seqs, self._kunya_seqs):
            specificity, best = _score_entry(
                query_seq, query, seqs, kunya_seqs, teknonym=teknonym, nasab_ref=not teknonym)
            if specificity:
                contained.append((specificity, entry))
            elif best:
                partial.append((best[0], best[1], entry))

        out: list[RijalEntry] = []
        seen: set[str] = set()

        def take(entry: RijalEntry) -> None:
            if entry.name not in seen:
                seen.add(entry.name)
                out.append(entry)

        if contained:
            top = max(s for s, _ in contained)
            for s, e in contained:
                if s == top:
                    take(e)
        if partial:
            # only the best reading: top coverage and, if any form is a prefix, prefix forms
            # only — so coincidental namesakes (محمد بن السائب الكلبي for «محمد بن بشر») are left
            # out of the homonym set the chain chooses among. And when the query is ITSELF a complete
            # man (a containment match exists), drop the non-prefix partials: they are forms that BURY
            # the query non-leading in a longer nasab — a descendant («إبراهيم بن محمد بن … بن جحش» for
            # «محمد بن عبد الله بن جحش») or the nephew, not the man — so the full name isn't false «مشترك».
            top_cov = max(c for c, _, _ in partial)
            any_prefix = any(p for c, p, _ in partial if c == top_cov)
            for c, pref, e in partial:
                if c == top_cov and (pref or (not any_prefix and not contained)):
                    take(e)
        # Prefer the real narrators: an obscure الإصابة/الثقات namesake must not sit in the homonym set a
        # chain chooses among (the terminal-صحابي promotion in analyze_isnad reads this) when a real man is
        # present — «أبي هريرة» is the Companion الدوسي, not a same-kunya محمد. Kept only when ALL are
        # coverage. Then the prominence prior drops a candidate far less narrated than the most prolific.
        out = _prefer_non_coverage(out)
        if apply_prominence:                          # …then the prominence prior, UNLESS the caller needs
            out = self._prefer_prominent(out)         # the full set (the mid-chain صحابي-demotion seeking a
        # تابعي homonym must still see the less-prolific man — see analyze_isnad).
        if max_results is not None and len(out) > max_results:
            out = []
        self._cand_cache[ckey] = out
        return out


def _read_jsonl(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_seed() -> list[dict]:
    """The bundled curated narrator set."""
    return list(_read_jsonl(Path(__file__).with_name("seed.jsonl")))


def load_entries(extra_path: str | None = None) -> list[dict]:
    """Seed entries, plus a full رجال JSONL when ``extra_path`` is given — with the seed RECONCILED
    into the built base (one canonical record per famous man, not the seed «هشام بن عروة» beside the
    built «هشام بن عروة بن الزبير الأسدي»; see :func:`app.rijal.dedup.reconcile_seed`)."""
    from app.rijal.dedup import reconcile_seed
    seed = load_seed()
    if extra_path:
        path = Path(extra_path)
        if path.exists():
            return reconcile_seed(seed, list(_read_jsonl(path)))
    return seed
