"""Optional LLM-extracted رجال & chains (``scripts.build_rijal_llm``) folded into the build pipeline.

**Gated on the files existing.** With no ``data/rijal_llm.jsonl`` / ``data/chains_llm.jsonl`` the
pipeline is exactly the regex pipeline — no behaviour change, no regression. Every LLM record was
validated *faithful* to its source at extraction time (a verbatim grade word; an isnād+matn that
reconstructs the original), and keeps its ``source_text`` for audit.

Three folds, three call-sites:

* :func:`load_llm_rijal` — ``build_rijal`` merges these like any other source (better grades, the
  death year, the compound kunya the terse regex dropped).
* :func:`llm_associations` — ``build_graph`` adds the شيوخ/تلاميذ **network** to the company profiles
  that :class:`app.rijal.canon.Canonicalizer` weighs to resolve «مشترك» (the strategic payoff).
* :func:`load_llm_chains` — the corpus parser uses a faithful re-segmentation for the chains the
  regex got wrong (matn leaked into the terminal narrator), keyed by :func:`text_key`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.parsing.normalize import normalize_for_search
from app.rijal.index import RijalIndex, _clean_tokens


def text_key(text: str) -> str:
    """A whitespace/diacritic-stable key for a hadith text — links a chain to its LLM segmentation,
    so the parser and the extractor agree on the same hadith regardless of spacing/tashkeel."""
    return hashlib.sha256(normalize_for_search(text or "").encode()).hexdigest()


def load_llm_rijal(path: str | Path) -> list[dict]:
    """``rijal_llm.jsonl`` → records in the ``rijal.jsonl`` shape (``grade`` = the verbatim grade
    word), so ``merge_source`` folds them in exactly like تقريب/الكاشف."""
    out: list[dict] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        name = (r.get("name") or "").strip()
        grade = (r.get("grade_word") or r.get("category") or "").strip()
        if len(name) < 3 or not grade:
            continue
        rec = {"name": name, "grade": grade, "source": r.get("source") or "LLM"}
        if r.get("kunya"):
            rec["kunya"] = r["kunya"]
        if r.get("death_year"):
            rec["death_year"] = r["death_year"]
        out.append(rec)
    return out


def llm_associations(path: str | Path, rijal: RijalIndex) -> dict[str, set[str]]:
    """Each LLM narrator's رجال canonical name → the tokens of his شيوخ+تلاميذ — the company that
    ``canon._pick`` weighs to resolve a «مشترك» bare name. Contributed only when the man resolves
    **unambiguously** (so we never anchor company onto the wrong homonym), exactly like
    :func:`app.rijal.tahdhib.tahdhib_associations`."""
    assoc: dict[str, set[str]] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        match = rijal.lookup((r.get("name") or "").strip())
        if match is None or match.ambiguous:
            continue
        tokens: set[str] = set()
        for who in (r.get("shuyukh") or []) + (r.get("talamidh") or []):
            if isinstance(who, str):
                tokens |= set(_clean_tokens(who))
        if tokens:
            assoc.setdefault(match.entry.name, set()).update(tokens)
    return assoc


def load_llm_chains(path: str | Path) -> dict[str, dict]:
    """``text_key(hadith text)`` → its faithful LLM segmentation ``{isnad, matn, narrators}``."""
    out: dict[str, dict] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        seg = json.loads(line)
        src = seg.get("source_text")
        if src and seg.get("isnad"):
            out[text_key(src)] = {"isnad": seg["isnad"], "matn": seg.get("matn") or "",
                                  "narrators": seg.get("narrators") or []}
    return out
