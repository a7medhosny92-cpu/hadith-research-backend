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

from app.parsing.normalize import normalize_for_search
from app.rijal.grades import classify

# Honorific ligatures (ﷺ ﵁ …), Quranic/honorific marks, and spelled-out eulogies.
_HONORIFIC_CH = re.compile(r"[﴾-﷿ؐ-ؚۖ-ۭ]")
_HONORIFIC_PHRASE = re.compile(
    r"رضي الله عنه[ام]*|صلى الله عليه وسلم|عليه السلام|رحمه الله|رضوان الله عليه"
)
# Tokens that are transmission verbs / spillover / non-discriminating connectors, never
# an identifying part of a name. «بن/ابن» are dropped so «خالد بن عمر» and «عمر بن الخطاب»
# don't look alike merely through the shared «بن».
_STOP = {normalize_for_search(w) for w in (
    "قال قالت يقول سمع سمعت يحدث أنه حدثنا حدثني أخبرنا أخبرني عن نا ثنا يعني المنبر بن ابن"
).split()}


def _clean_tokens(name: str) -> set[str]:
    text = _HONORIFIC_PHRASE.sub(" ", _HONORIFIC_CH.sub(" ", name or ""))
    return {t for t in normalize_for_search(text).split() if t and t not in _STOP}


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
        }


class RijalIndex:
    """In-memory narrator lookup (linear; the corpus of named narrators is small)."""

    def __init__(self, entries: Iterable[dict] | None = None) -> None:
        self._entries: list[RijalEntry] = []
        self._forms: list[list[set[str]]] = []  # token set per name form (canonical + aliases)
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
            )
            forms = [t for t in (_clean_tokens(f) for f in (entry.name, *entry.aliases)) if t]
            self._entries.append(entry)
            self._forms.append(forms)
            n += 1
        return n

    def count(self) -> int:
        return len(self._entries)

    def lookup(self, name: str, *, min_overlap: float = 0.6) -> RijalMatch | None:
        """Best narrator match, or ``None``.

        A name *form* fully contained in the query (e.g. query «عمر بن الخطاب علي»
        contains «عمر بن الخطاب») is a confident hit; the most specific such form
        wins, which keeps a man distinct from a longer namesake (his son «عبد الله
        بن عمر»). Only when no form is contained do we fall back to fuzzy overlap.
        Equally-specific rivals (سفيان ↦ ابن عيينة/الثوري) are flagged ambiguous.
        """
        query = _clean_tokens(name)
        if not query:
            return None

        contained: list[tuple[int, RijalEntry]] = []   # (specificity, entry)
        partial: list[tuple[float, RijalEntry]] = []    # (overlap, entry)
        for entry, forms in zip(self._entries, self._forms):
            specificity = 0
            best_overlap = 0.0
            for form in forms:
                # a bare single-token form (an ism like «عمر») can't confidently identify
                # a more fully-named query («خالد بن عمر») — only an exact bare-name query
                # («عن أنس») may match it. This kills score-1.0 over-grading.
                if len(form) == 1 and len(query) > 1:
                    continue
                shared = len(query & form)
                if not shared:
                    continue
                if shared == len(form):  # form ⊆ query
                    specificity = max(specificity, len(form))
                best_overlap = max(best_overlap, shared / min(len(query), len(form)))
            if specificity:
                contained.append((specificity, entry))
            elif best_overlap >= min_overlap:
                partial.append((round(best_overlap, 3), entry))

        if contained:
            contained.sort(key=lambda pair: -pair[0])
            top = contained[0][0]
            best = contained[0][1]
            alternatives = [e.name for s, e in contained if s == top and e.name != best.name]
            return RijalMatch(best, 1.0, bool(alternatives), alternatives[:3])

        if partial:
            partial.sort(key=lambda pair: -pair[0])
            top, best = partial[0]
            alternatives = [
                e.name for score, e in partial if top - score < 1e-6 and e.name != best.name
            ]
            return RijalMatch(best, top, bool(alternatives), alternatives[:3])

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
