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


def _clean_seq(name: str) -> list[str]:
    """Folded name tokens **in order**, honorifics/connectors dropped. A token repeated NON-adjacently
    (a distant ancestor) is dropped, but an ADJACENT repeat is KEPT: «معاذ بن معاذ» (ism = father's
    name) is a real two-token name (معاذ بن معاذ العنبري القاضي), NOT the bare «معاذ» that would match
    every معاذ بن فلان and make a famous narrator «مشترك» among twenty men.

    Kunya cases are unified (أبو/أبا/أبي → أبو) before «بن» is dropped, so «أبي موسى»
    matches «أبو موسى»; «أبي بن …» stays أُبَيّ (a name, not a kunya)."""
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


# Curated, closed anchor sets (folded once): a high-status narrator whose رجال entry carries NO grade
# must not read «مجهول». Each form is ≥2 distinctive tokens; an entry whose name CONTAINS one is graded
# accordingly. See app/rijal/companions.py.
_COMPANION_FORMS = [f for f in (frozenset(_clean_tokens(c)) for c in MAJOR_COMPANIONS) if len(f) >= 2]
_TABII_FORMS = [f for f in (frozenset(_clean_tokens(c)) for c in MAJOR_TABIIN) if len(f) >= 2]


def _anchor_grade(name_tokens: set[str]) -> tuple[str, int] | None:
    """If the name contains a major Companion → («صحابي», 10); a major تابعي ثقة → («ثقة», 9); else
    ``None``. Only consulted for an otherwise-ungraded entry (see ``RijalIndex.add``)."""
    if any(f <= name_tokens for f in _COMPANION_FORMS):
        return "صحابي", RANKS["صحابي"]
    if any(f <= name_tokens for f in _TABII_FORMS):
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
            if query_seq[:len(seq)] == seq:        # … as its LEADING run (the cited man), not an
                specificity = max(specificity, len(form))   # ancestor buried in the nasab: «محمد
                # بن … بن أنس بن مالك» is not أنس, «عبد الله بن عمر بن الخطاب» is the son not عمر.
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


class RijalIndex:
    """In-memory narrator lookup (linear; the corpus of named narrators is small)."""

    def __init__(self, entries: Iterable[dict] | None = None) -> None:
        self._entries: list[RijalEntry] = []
        self._form_seqs: list[list[list[str]]] = []   # name + alias token-seqs (full matching)
        self._kunya_seqs: list[list[list[str]]] = []   # reverse-only forms: teknonyms + kunya
        self._cache: dict[tuple[str, float], "RijalMatch | None"] = {}  # memoise lookups
        if entries:
            self.add(entries)

    def add(self, entries: Iterable[dict]) -> int:
        n = 0
        for raw in entries:
            category, rank = classify(raw.get("grade") or "")
            # A Companion's bio («أحد العشرة أسلم قديمًا …») sometimes leaks into his NAME, not the grade,
            # so a major صحابي (عبد الرحمن بن عوف) is mis-graded «مجهول» → a chain through him reads «راوٍ
            # مجهول». Recover صحابي from his own name when the grade is silent (only ever PROMOTES).
            if category == "غير معروف":
                # A high-status narrator must not read «مجهول» just because his grade wasn't extracted.
                # (1) A curated, CLOSED anchor — a major Companion (→صحابي) or a major تابعي ثقة (→ثقة);
                # these are the well-known referents, documentary not guessed (app/rijal/companions.py).
                # (2) Else recover a POSITIVE grade that leaked into his NAME (عبد الرحمن بن عوف «أحد
                # العشرة …») — never a negative one, which could sink a sound chain on a coincidental word.
                anchor = _anchor_grade(_clean_tokens(raw["name"]))
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
        self._cache.clear()   # entries changed → drop memoised lookups
        return n

    def count(self) -> int:
        return len(self._entries)

    def lookup(self, name: str, *, min_overlap: float = 0.6) -> RijalMatch | None:
        """Best narrator match, or ``None`` (memoised — the same name recurs across chains)."""
        key = (name, min_overlap)
        if key not in self._cache:
            self._cache[key] = self._lookup(name, min_overlap=min_overlap)
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
            group = _prefer_non_coverage([e for s, e in contained if s == top])
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
            group = _prefer_non_coverage(
                [e for cov, pref, ln, e in partial if cov == top_cov and pref == top_pref])
            best_e = group[0]
            alternatives = [e.name for e in group if e.name != best_e.name]
            agreed = all(e.category == best_e.category for e in group)
            return RijalMatch(best_e, 1.0, bool(alternatives), alternatives[:3], grade_agreed=agreed)

        return None

    def candidates(self, name: str, *, max_results: int | None = 40) -> list[RijalEntry]:
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
        query_seq = _clean_seq(name)
        query = set(query_seq)
        if not query or (len(query) == 1 and query_seq[0] in _NON_IDENTIFYING):
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
        if max_results is not None and len(out) > max_results:
            return []
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
    """Seed entries, plus a full رجال JSONL when ``extra_path`` is given."""
    entries = load_seed()
    if extra_path:
        path = Path(extra_path)
        if path.exists():
            entries.extend(_read_jsonl(path))
    return entries
