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

from app.search import HadithIndex, SearchHit, SharhHit, SharhIndex

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


def _complete_sharh(sharh: list[SharhHit], sharh_index: SharhIndex) -> list[dict]:
    """Turn the ranked شرح chunks into source dicts carrying the *complete* passage.

    For by-number commentary we re-join every chunk of that hadith's شرح (and drop
    duplicate chunks of the same commentary on the same hadith); by-chapter شرح has
    no hadith number to join on, so its own chunk text is kept as-is.
    """
    out: list[dict] = []
    seen: set[tuple[int, int]] = set()
    for s in sharh:
        d = s.to_dict()
        if s.hadith_number is not None:
            key = (s.book_id, s.hadith_number)
            if key in seen:
                continue
            seen.add(key)
            full = sharh_index.full_text(s.book_id, s.hadith_number)
            if full:
                d["text"] = full
        out.append(d)
    return out


def answer_question(
    question: str,
    hadith_index: HadithIndex,
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

    sharh: list[SharhHit] = []
    if hadith and k_sharh:
        top = hadith[0]
        if top.number is not None:
            sharh = sharh_index.search(
                question, base_id=top.book_id, hadith_number=top.number, limit=k_sharh
            ) or sharh_index.by_hadith(top.book_id, top.number, limit=k_sharh)
        if not sharh:
            sharh = sharh_index.search(question, limit=k_sharh)

    hadith_sources = [h.to_dict() for h in hadith]
    sharh_sources = _complete_sharh(sharh, sharh_index)

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
    }
