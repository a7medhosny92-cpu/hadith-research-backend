"""Cluster search hits that are the *same report* (نفس الحديث) so a query doesn't list the
same hadith many times across books.

Greedy single-pass clustering by folded-matn **overlap coefficient** (shared ÷ smaller):
each hit joins the first existing group whose representative it overlaps by ``threshold``,
else it starts a new group. Hits arrive in relevance order, so the first (most relevant)
member naturally heads its group. Clustering is capped for cost; the tail stays as
singletons. This is a display aid for /search — the authoritative survey is /takhrij.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.parsing.normalize import normalize_for_search

if TYPE_CHECKING:
    from app.search import SearchHit


def _toks(matn: str) -> frozenset[str]:
    return frozenset(normalize_for_search(matn or "").split())


def cluster_reports(
    hits: list["SearchHit"], *, threshold: float = 0.82, cap: int = 500
) -> list[list["SearchHit"]]:
    """Group ``hits`` into reports; returns a list of member-lists (relevance order kept)."""
    groups: list[dict] = []   # {"rep": frozenset, "members": [hit]}
    for hit in hits[:cap]:
        toks = _toks(hit.matn)
        best, best_ov = None, 0.0
        if toks:
            for g in groups:
                inter = len(toks & g["rep"])
                if not inter:
                    continue
                ov = inter / min(len(toks), len(g["rep"]))
                if ov > best_ov:
                    best, best_ov = g, ov
        if best is not None and best_ov >= threshold:
            best["members"].append(hit)
        else:
            groups.append({"rep": toks, "members": [hit]})
    # anything beyond the clustering cap is kept as its own (ungrouped) report
    for hit in hits[cap:]:
        groups.append({"rep": _toks(hit.matn), "members": [hit]})
    return [g["members"] for g in groups]
