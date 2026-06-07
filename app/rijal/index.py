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


def _order_ok(q_seq: list[str], f_seq: list[str], shared: set[str]) -> bool:
    """True if the shared tokens appear in the same relative order in both — so a query
    «يزيد بن جابر» does NOT match a form «جابر بن يزيد» (a different man)."""
    return [t for t in q_seq if t in shared] == [t for t in f_seq if t in shared]


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
        self._kunya_seqs: list[list[str] | None] = []  # the kunya (reverse-containment only)
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
            # The name + its aliases are matched in full (containment either way). The kunya
            # is kept apart: a chain may cite a man BY his kunya (أبو هريرة), but a common
            # kunya («أبو بكر») must NOT match a fuller name that merely contains it.
            seqs = [s for s in (_clean_seq(f) for f in (entry.name, *entry.aliases)) if s]
            kunya = _clean_seq(entry.kunya) if entry.kunya else None
            self._entries.append(entry)
            self._form_seqs.append(seqs)
            self._kunya_seqs.append(kunya or None)
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
        for entry, seqs, kunya in zip(self._entries, self._form_seqs, self._kunya_seqs):
            specificity = 0
            best: tuple[int, int] | None = None   # (cover, form_len) for query ⊆ form
            for seq in seqs:
                form = set(seq)
                # a bare single-token form (an ism like «عمر») can't confidently identify
                # a more fully-named query («خالد بن عمر») — only an exact bare-name query
                # («عن أنس») may match it. This kills score-1.0 over-grading.
                if len(form) == 1 and len(query) > 1:
                    continue
                shared = query & form
                # the shared tokens must be in the same order in both, else it's a different
                # man whose name is the reverse («يزيد بن جابر» vs «جابر بن يزيد»)
                if not shared or not _order_ok(query_seq, seq, shared):
                    continue
                if len(shared) == len(form):           # form ⊆ query → the entry's name is in the query
                    specificity = max(specificity, len(form))
                elif len(shared) == len(query):        # query ⊆ form → cited name is a partial of this entry
                    cand = (len(shared), len(form))
                    if best is None or cand[0] > best[0] or (cand[0] == best[0] and cand[1] < best[1]):
                        best = cand
                # else: neither contains the other → coincidental shared token(s), not a match
            # the kunya identifies a man only when the chain cites him BY it (query ⊆ kunya);
            # a common kunya as a fragment of a fuller name must not match (أبو بكر بن أبي شيبة
            # is not «الزهري» merely because الزهري's kunya is أبو بكر).
            if kunya:
                kf = set(kunya)
                shared = query & kf
                if shared and len(shared) == len(query) and _order_ok(query_seq, kunya, shared):
                    cand = (len(shared), len(kf))
                    if best is None or cand[0] > best[0] or (cand[0] == best[0] and cand[1] < best[1]):
                        best = cand
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
