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
from app.rijal.grades import classify

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
# (أبو/أبي/أبا), «أم», or «عبد». We refuse to match rather than guess: «أبي» would otherwise
# hit «عائشة بنت أبي بكر» through «بنت أبي بكر», and «عبد» any «عبد الله».
_NON_IDENTIFYING = {normalize_for_search(w) for w in "أبو أبي أبا أم عبد".split()}


def _clean_seq(name: str) -> list[str]:
    """Folded name tokens **in order**, de-duplicated, honorifics/connectors dropped.

    Kunya cases are unified (أبو/أبا/أبي → أبو) before «بن» is dropped, so «أبي موسى»
    matches «أبو موسى»; «أبي بن …» stays أُبَيّ (a name, not a kunya)."""
    text = _HONORIFIC_PHRASE.sub(" ", _HONORIFIC_CH.sub(" ", name or ""))
    seen: set[str] = set()
    out: list[str] = []
    for t in fold_kunya(normalize_for_search(text).split()):
        if t and t not in _STOP and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _clean_tokens(name: str) -> set[str]:
    return set(_clean_seq(name))


# Kunya particles after folding (أبو/أبا/أبي → ابو, أم → ام). A form that *starts* with
# one is a teknonym — «أبو بكر», «أم سلمة», «أبو عبد الله» — and must be matched
# reverse-only (the chain has to cite the man BY it), never glued onto a longer, different
# name that merely contains it: «أبو بكر بن أبي شيبة» (a حافظ) is not «أبو بكر» the Companion.
_KUNYA_PARTICLES = {normalize_for_search("أبو"), normalize_for_search("أم")}


def _is_kunya_form(seq: list[str]) -> bool:
    """True if ``seq`` is a teknonym (leads with a kunya particle) — matched reverse-only."""
    return bool(seq) and seq[0] in _KUNYA_PARTICLES


def _order_ok(q_seq: list[str], f_seq: list[str], shared: set[str]) -> bool:
    """True if the shared tokens appear in the same relative order in both — so a query
    «يزيد بن جابر» does NOT match a form «جابر بن يزيد» (a different man)."""
    return [t for t in q_seq if t in shared] == [t for t in f_seq if t in shared]


def _score_entry(
    query_seq: list[str], query: set[str], seqs: list[list[str]], kunya_seqs: list[list[str]]
) -> tuple[int, tuple[int, int] | None]:
    """Score one entry against the query.

    Returns ``(specificity, best_partial)`` where ``specificity > 0`` means an entry form
    is fully inside the query (containment — the entry's name appears in the cited name),
    and ``best_partial = (cover, form_len)`` means the cited name is a partial of an entry
    form (query ⊆ form). Either may be falsy. Teknonym forms (``kunya_seqs``) match
    reverse-only — they can only ever contribute a partial, never a containment.
    """
    specificity = 0
    best: tuple[int, int] | None = None
    for seq in seqs:
        form = set(seq)
        # a bare single-token form (an ism like «عمر») can't confidently identify a more
        # fully-named query («خالد بن عمر») — only an exact bare-name query may match it.
        if len(form) == 1 and len(query) > 1:
            continue
        shared = query & form
        if not shared or not _order_ok(query_seq, seq, shared):
            continue
        if len(shared) == len(form):               # form ⊆ query → entry's name is in the query
            specificity = max(specificity, len(form))
        elif len(shared) == len(query):            # query ⊆ form → cited name is a partial
            cand = (len(shared), len(form))
            if best is None or cand[0] > best[0] or (cand[0] == best[0] and cand[1] < best[1]):
                best = cand
        # else: neither contains the other → coincidental shared token(s), not a match
    for kseq in kunya_seqs:                         # teknonyms: only query ⊆ kunya (reverse)
        kf = set(kseq)
        shared = query & kf
        if shared and len(shared) == len(query) and _order_ok(query_seq, kseq, shared):
            cand = (len(shared), len(kf))
            if best is None or cand[0] > best[0] or (cand[0] == best[0] and cand[1] < best[1]):
                best = cand
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


@dataclass(slots=True)
class RijalMatch:
    entry: RijalEntry
    score: float
    ambiguous: bool
    alternatives: list[str]

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
            "alternatives": self.alternatives,
            "opinions": self.entry.opinions,
        }


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
            )
            # Non-teknonym names/aliases match by containment either way; teknonyms (a
            # name/alias/kunya leading with أبو/أم) are kept apart and matched reverse-only:
            # a chain may cite a man BY his kunya (أبو هريرة), but a common kunya («أبو بكر»)
            # must NOT glue onto a fuller, different name that merely contains it.
            forms = [s for s in (_clean_seq(f) for f in (entry.name, *entry.aliases)) if s]
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

        contained: list[tuple[int, RijalEntry]] = []        # (specificity, entry) — name ⊆ query
        partial: list[tuple[int, int, RijalEntry]] = []     # (cover, form_len, entry) — query ⊆ name
        for entry, seqs, kunya_seqs in zip(self._entries, self._form_seqs, self._kunya_seqs):
            specificity, best = _score_entry(query_seq, query, seqs, kunya_seqs)
            if specificity:
                contained.append((specificity, entry))
            elif best:
                partial.append((best[0], best[1], entry))

        if contained:
            contained.sort(key=lambda pair: -pair[0])
            top = contained[0][0]
            best_e = contained[0][1]
            alternatives = [e.name for s, e in contained if s == top and e.name != best_e.name]
            return RijalMatch(best_e, 1.0, bool(alternatives), alternatives[:3])

        if partial:
            partial.sort(key=lambda t: (-t[0], t[1]))   # cover most of the query, then shortest name
            top_cov, top_len, best_e = partial[0]
            # ties are only among names equally close to the query (same coverage and length) —
            # real homonyms like سعيد ↦ ابن المسيب/ابن جبير, flagged for the reader to resolve.
            alternatives = [
                e.name for cov, ln, e in partial
                if cov == top_cov and ln == top_len and e.name != best_e.name
            ]
            return RijalMatch(best_e, 1.0, bool(alternatives), alternatives[:3])

        return None

    def candidates(self, name: str) -> list[RijalEntry]:
        """The distinct known men who could be ``name`` — the homonym set for context-based
        تمييز المهمل («the chain before the name»).

        Unlike :meth:`lookup`, which collapses to one best answer, this returns *all* the
        real namesakes — the most-specific contained name(s) AND every best-covering partial
        (fuller-named) homonym — so the chain's company can choose between them, e.g. «محمد
        بن بشر» [متروك] vs «محمد بن بشر العبدي» [ثقة]. Capped: a bare ism with dozens of
        bearers is too generic for the chain to resolve, so we return nothing then.
        """
        query_seq = _clean_seq(name)
        query = set(query_seq)
        if not query or (len(query) == 1 and query_seq[0] in _NON_IDENTIFYING):
            return []
        contained: list[tuple[int, RijalEntry]] = []
        partial: list[tuple[int, RijalEntry]] = []
        for entry, seqs, kunya_seqs in zip(self._entries, self._form_seqs, self._kunya_seqs):
            specificity, best = _score_entry(query_seq, query, seqs, kunya_seqs)
            if specificity:
                contained.append((specificity, entry))
            elif best:
                partial.append((best[0], entry))

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
            top_cov = max(c for c, _ in partial)
            for c, e in partial:
                if c == top_cov:
                    take(e)
        return out if len(out) <= 40 else []


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
