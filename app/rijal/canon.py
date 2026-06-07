"""Canonicalise a narrator's surface form to one identity (توحيد الاسم/الكنية/اللقب).

The same man appears in chains as a bare ism (أنس), a full nasab (أنس بن مالك), a
nisba (عطاء بن يزيد الليثي), a kunya (أبو هريرة) or a laqab (الفاروق) — forms that may
share *no tokens at all*. Left alone, each becomes a separate node in the network. This
maps every form back to the رجال database's canonical name, so they collapse into one.

The rule is **merge only when certain**:

* a unique authority match — full name, alias, kunya, or a uniquely-contained name with
  its tokens in the right order — is taken (``lookup`` already does this and flags ties);
* an *ambiguous* bare name (سعيد ↦ ابن المسيب vs ابن جبير) is resolved from the chain it
  sits in: the candidate whose recorded company best fits the chain's other narrators;
* if nothing decides it, the **surface form is kept unchanged**.

So we never fuse two different men, and never make the graph worse than before. The
``associations`` (each canonical → the tokens of the company it keeps) are derived from a
first, confident-only pass over the corpus — see ``scripts.build_graph``.
"""

from __future__ import annotations

from app.rijal.index import RijalIndex, _clean_seq, _clean_tokens


class Canonicalizer:
    """Resolve narrator surface forms to a single canonical name via the رجال authority."""

    def __init__(
        self, rijal: RijalIndex, associations: dict[str, set[str]] | None = None
    ) -> None:
        self._rijal = rijal
        self._assoc = associations or {}
        self._resolve_cache: dict[str, tuple[str | None, tuple[str, ...]]] = {}
        self._tok_cache: dict[str, frozenset[str]] = {}

    def tokens(self, name: str) -> frozenset[str]:
        """Cleaned name tokens (cached) — the token space the authority matches in."""
        t = self._tok_cache.get(name)
        if t is None:
            t = self._tok_cache[name] = frozenset(_clean_tokens(name))
        return t

    def _resolve(self, surface: str) -> tuple[str | None, tuple[str, ...]]:
        """``(confident_canonical, candidates)`` — context-free, cached per surface.

        A certain, unambiguous hit returns ``(name, ())``; several men sharing the name
        return ``(None, candidates)`` for the context tier; anything weaker (only a fuzzy
        partial, or unknown) returns ``(None, ())`` so the surface form is kept.
        """
        match = self._rijal.lookup(surface)
        if match is None or match.score < 1.0:
            return (None, ())
        if not match.ambiguous:
            return (match.entry.name, ())
        return (None, tuple(dict.fromkeys([match.entry.name, *match.alternatives])))

    def canonical(self, surface: str, context: frozenset[str] = frozenset()) -> str:
        """The canonical name for ``surface``; falls back to ``surface`` when unsure.

        ``context`` is the cleaned token set of the *other* narrators in the same chain,
        used only to break ties between equally-named men.
        """
        seq = _clean_seq(surface)
        if not seq:
            return surface
        key = " ".join(seq)            # order-preserving (يزيد بن جابر ≠ جابر بن يزيد)
        res = self._resolve_cache.get(key)
        if res is None:
            res = self._resolve_cache[key] = self._resolve(surface)
        canon, candidates = res
        if canon:
            return canon
        if candidates:
            picked = self._pick(candidates, context)
            if picked:
                return picked
        return surface

    def _pick(self, candidates: tuple[str, ...], context: frozenset[str]) -> str | None:
        """The candidate whose recorded company best overlaps the chain context — only
        when there is a *strict* unique winner with real overlap; else ``None``."""
        if not context:
            return None
        best, best_score, tie = None, 0, False
        for cand in candidates:
            score = len(self._assoc.get(cand, frozenset()) & context)
            if score > best_score:
                best, best_score, tie = cand, score, False
            elif score == best_score and score > 0:
                tie = True
        return best if best and best_score > 0 and not tie else None
