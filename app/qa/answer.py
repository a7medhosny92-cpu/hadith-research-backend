"""Compose a cited answer from retrieved hadith and scholarly commentary (شرح).

This is the retrieval + grounding core of ``/ask``. It is **extractive by default**
— no LLM dependency — so it runs anywhere: it returns the most relevant hadith with
its grade and citation, plus the commentary the ʿulamāʾ wrote on that exact hadith.

If a ``synthesize`` callable is supplied (e.g. a litellm/Ollama wrapper in
production) it is handed the same retrieved sources to write a grounded prose
answer; the sources are always returned so the answer stays verifiable.
"""

from __future__ import annotations

from typing import Callable

from app.qa.rulings import collect_rulings
from app.search import HadithIndex, HybridSearcher, SearchHit, SharhHit, SharhIndex

#: Given (question, hadith_sources, sharh_sources) → a grounded prose answer.
Synthesizer = Callable[[str, list[dict], list[dict]], str]


def _citation(hit: SearchHit) -> str:
    parts = [hit.collection]
    if hit.number is not None:
        parts.append(f"رقم {hit.number}")
    if hit.page is not None:
        parts.append(f"ص {hit.page}")
    return " - ".join(parts)


def _extractive_answer(hadith: list[SearchHit], sharh: list[dict]) -> str:
    if not hadith:
        return "لم أعثر على حديثٍ مطابقٍ في النصوص المتوفّرة."
    top = hadith[0]
    lines = [f"ورد في {_citation(top)}: «{top.matn}»."]
    if top.grade:
        lines.append(f"الحكم: {top.grade}.")
    if sharh:
        s = sharh[0]
        body = s.get("text") or s.get("excerpt") or ""
        # Be honest about whether the commentary explains *this* hadith or is merely
        # related: only passages linked to the top hadith may claim to be its شرح.
        if s.get("hadith_number") == top.number and s.get("base_id") == top.book_id:
            lines.append(f"\nمن كلام أهل العلم في شرح هذا الحديث — {s.get('sharh')}:\n{body}")
        else:
            ref = s.get("sharh") + (
                f" (عند الحديث رقم {s['hadith_number']})" if s.get("hadith_number") else ""
            )
            lines.append(f"\nومن الشروح ذات الصلة بالموضوع — {ref}:\n{body}")
    return "\n".join(lines)


def _linked_sharh(
    question: str, hadith: list[SearchHit], sharh_index: SharhIndex, k_sharh: int
) -> list["SharhHit"]:
    """Find commentary that explains one of the retrieved hadith.

    Walk the ranked hadith (not just the first): for each, look for شرح tied to that
    exact hadith — by question relevance, else any of its linked passages. Return the
    first hadith's commentary we find, so the answer never falls back to unrelated شرح
    just because the single top hadith happens to be uncommented. Only if *none* of the
    retrieved hadith are commented do we do a general شرح search.
    """
    if not hadith or not k_sharh:
        return []
    for top in hadith:
        if top.number is None:
            continue
        found = sharh_index.search(
            question, base_id=top.book_id, hadith_number=top.number, limit=k_sharh
        ) or sharh_index.by_hadith(top.book_id, top.number, limit=k_sharh)
        if found:
            return found
    return sharh_index.search(question, limit=k_sharh)


def _complete_sharh(sharh: list[SharhHit], sharh_index: SharhIndex) -> list[dict]:
    """Turn the ranked شرح chunks into source dicts carrying the *complete* passage.

    Each chunk names the passage it belongs to via its anchor ``page_id``; we re-join
    all of that passage's chunks (so the full discourse is shown, not a fragment) and
    drop duplicate chunks of the same passage. Works for by-number and by-chapter شرح.
    """
    out: list[dict] = []
    seen: set[tuple[int, int]] = set()
    for s in sharh:
        d = s.to_dict()
        if s.page_id is not None:
            key = (s.book_id, s.page_id)
            if key in seen:
                continue
            seen.add(key)
            full = sharh_index.full_passage(s.book_id, s.page_id)
            if full:
                d["text"] = full
        out.append(d)
    return out


def answer_question(
    question: str,
    hadith_index: HadithIndex | HybridSearcher,
    sharh_index: SharhIndex,
    *,
    k_hadith: int = 5,
    k_sharh: int = 3,
    synthesize: Synthesizer | None = None,
) -> dict:
    """Retrieve relevant hadith + linked commentary and return a cited answer.

    Commentary is sought for the top hadith first by question relevance within that
    exact hadith's شرح, then any commentary linked to it, then a general شرح search —
    so the answer cites scholarship tied to the matched hadith when possible.
    """
    hadith = hadith_index.search(question, limit=k_hadith)
    sharh = _linked_sharh(question, hadith, sharh_index, k_sharh)

    hadith_sources = [h.to_dict() for h in hadith]
    sharh_sources = _complete_sharh(sharh, sharh_index)

    # Scholars' rulings on the top hadith, gathered from its matn and its شروح,
    # ordered by era (طبقة) — so divergent verdicts are surfaced, oldest first.
    ruling_texts = ([hadith[0].matn] if hadith else []) + [
        s.get("text") or s.get("excerpt") or "" for s in sharh_sources
    ]
    rulings = collect_rulings(ruling_texts)

    if synthesize is not None:
        answer, mode = synthesize(question, hadith_sources, sharh_sources), "llm"
    else:
        answer, mode = _extractive_answer(hadith, sharh_sources), "extractive"

    return {
        "question": question,
        "answer": answer,
        "mode": mode,
        "hadith": hadith_sources,
        "sharh": sharh_sources,
        "rulings": rulings,
    }
