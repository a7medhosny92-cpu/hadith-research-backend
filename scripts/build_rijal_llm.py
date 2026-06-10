"""LLM-assisted, **faithful** extraction — a build-time pass over the cached books.

Two modes, one tool, one infrastructure (config LLM · hash cache · dry-run · validation):

* ``--mode rijal``  — turn each تقريب/الكاشف/تهذيب tarjama into a structured record
  ``{name, kunya, grade_word, category, death_year, tabaqa, shuyukh[], talamidh[], note}``.
  The terse-book regex (``rijal_extract``) drops the شيوخ/تلاميذ **network** and trips on the
  long tail of natural language (Companions by description, enmity-accusations, hamza, ضبط,
  compound kunyas, grade-after-network). The LLM reads the language; the network it unlocks is
  the lever for resolving the «مشترك» homonyms.

* ``--mode chains`` — segment a hadith into isnād / matn / ordered narrators, **only** for the
  chains the regex parser flags as suspicious (0 narrators, matn leaked into the terminal node,
  a verse ﴿…﴾ or a matn word inside a node, …). Fixes the truncations/leaks without hand-coding
  more matn-boundary regex.

**Faithfulness is enforced, not trusted.** This is sacred text (نصّ الحديث) and authoritative
الجرح والتعديل — so the LLM only *segments/transcribes*, never authors:

* the prompt forbids inventing or rewriting; it must copy verbatim spans of the source;
* every result is **validated against the source** and **rejected** (→ keep the regex output) if
  it doesn't hold: a grade word must occur in the tarjama; an isnād+matn must reconstruct the
  original token-for-token; each narrator must be a substring of the isnād.

Nothing here runs at request time — it is a one-time, cached, resumable build step. Run it on
your machine with your configured engine; ``--dry-run`` and ``--sample N`` let you preview first.

    python -m scripts.build_rijal_llm --mode rijal  --sample 20 --dry-run
    python -m scripts.build_rijal_llm --mode rijal              # uses llm_extract_model (gemma4:31b-cloud)
    python -m scripts.build_rijal_llm --mode chains --model ollama/qwen2.5:7b
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Callable, Iterable, Iterator

from app.config import Settings
from app.parsing.html_clean import clean_block
from app.parsing.normalize import normalize_for_search
from app.parsing.rijal_extract import (
    _BOUNDARY, _century_from_tabaqa, _death_year, _first_entry_page, _tabaqa_number,
    arabic_digits_to_int,
)
from app.rijal.grades import classify

# Where the books and the cache live.
BOOKS = Path("data/raw/turath/books")
CACHE_DB = Path("data/llm_cache.db")
RIJAL_BOOKS = {"تقريب التهذيب": 8609, "الكاشف": 2171, "تهذيب الكمال": 3722}
CHAIN_BOOKS = {"صحيح البخاري": 1284, "صحيح مسلم": 1727}
PROMPT_VERSION = "v1"          # bump to invalidate the cache when a prompt changes

# Categories grades.classify may emit — a grade word the LLM reports must map into this set,
# otherwise we treat the extraction as untrusted and fall back to the regex.
_KNOWN_CATEGORIES = {
    "صحابي", "ثقة", "صدوق", "صدوق له أوهام", "مقبول", "لين", "مستور",
    "مجهول", "ضعيف", "متروك", "كذاب", "غير معروف",
}


# ── LLM plumbing (litellm via the project's config) ───────────────────────────────────────────
def _resolve_model(settings: Settings, engine: str | None, model: str | None = None) -> tuple[str, str | None]:
    """(model, api_base) for the extraction; export keys so litellm can authenticate.

    Precedence: explicit ``model`` > ``engine`` (its configured /ask brain) > ``llm_extract_model``
    (the default — so this tool and update.bat use the dedicated extraction model out of the box,
    with no .env juggling). The api_base is the local Ollama server for any ``ollama/…`` model,
    else None (a hosted cloud endpoint litellm reaches directly)."""
    if settings.anthropic_api_key:
        os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
    if settings.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)
    if model:
        chosen = model
    elif engine == "local":
        chosen = settings.llm_local_model
    elif engine == "remote":
        chosen = settings.llm_remote_model
    else:
        chosen = settings.llm_extract_model
    api_base = settings.ollama_api_base if chosen.startswith("ollama/") else None
    return chosen, api_base


def _make_llm(settings: Settings, model: str, api_base: str | None) -> Callable[[str], str]:
    """A ``prompt -> raw_text`` callable for ``model``. litellm is imported lazily (optional 'llm' extra)."""
    def call(prompt: str) -> str:
        import litellm  # lazy
        resp = litellm.completion(
            model=model, api_base=api_base, temperature=0.0, timeout=settings.llm_timeout,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp["choices"][0]["message"]["content"]

    return call


def _parse_json(raw: str) -> dict | None:
    """Pull the first JSON object out of an LLM reply (tolerates ```json fences / prose)."""
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


# ── hash cache (idempotent, resumable; one LLM call per unique source) ─────────────────────────
class Cache:
    def __init__(self, path: Path = CACHE_DB, model: str = "") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(str(path))
        self._con.execute("CREATE TABLE IF NOT EXISTS llm(k TEXT PRIMARY KEY, v TEXT)")
        self.model = model                               # part of the key — a cached value IS this
                                                         # model's output, so switching models re-extracts
                                                         # (and an A/B compare reads the right answers)

    def key(self, mode: str, source: str) -> str:
        return hashlib.sha256(f"{mode}|{PROMPT_VERSION}|{self.model}|{source}".encode()).hexdigest()

    def get(self, k: str) -> dict | None:
        row = self._con.execute("SELECT v FROM llm WHERE k=?", (k,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, k: str, v: dict) -> None:
        self._con.execute("INSERT OR REPLACE INTO llm(k, v) VALUES (?, ?)", (k, json.dumps(v, ensure_ascii=False)))
        self._con.commit()


# ── faithfulness validation (the guardrail — pure, unit-testable, no LLM) ──────────────────────
def _folded_tokens(text: str) -> list[str]:
    return normalize_for_search(text or "").split()


def _regex_death_year(source: str) -> int | None:
    """The death year the TRUSTED regex computes (#122): the spelled/digit year, with the dropped
    hundreds recovered from the طبقة. The LLM transcribes the literal year («من العاشرة … مات سنة
    ست وثلاثين» → 36) but skips the century rule, so we override its death_year with this — a
    century-naive year (off by ~200) would corrupt the same-man dedup, which keys on death ±20."""
    year = _death_year(source)
    if year is not None and year < 100:
        year = _century_from_tabaqa(year, _tabaqa_number(source))
    return year


def validate_rijal(rec: dict, source: str) -> dict | None:
    """Trust an LLM rijal record only if it is faithful to the tarjama: a stated grade word must
    occur in the source and map to a known category; otherwise return None (→ keep the regex)."""
    if not isinstance(rec, dict) or not (rec.get("name") or "").strip():
        return None
    src = normalize_for_search(source)
    word = (rec.get("grade_word") or "").strip()
    if word:
        if normalize_for_search(word) not in src:        # invented grade → reject
            return None
        category, rank = classify(word)
        if category not in _KNOWN_CATEGORIES:
            return None
    else:
        category, rank = "غير معروف", None
    # شيوخ/تلاميذ must each actually appear in the tarjama (no invented company)
    def _kept(names) -> list[str]:
        # a company name is kept only if it actually occurs in the tarjama — substring on the folded
        # text, so «الزهري» still matches the source's «والزهري» (و-prefixed) without being invented.
        out = []
        for n in names or []:
            fn = normalize_for_search(n) if isinstance(n, str) else ""
            if fn and len(fn) >= 2 and fn in src:
                out.append(n.strip())
        return out
    rec = dict(rec)
    rec["category"] = category
    rec["shuyukh"], rec["talamidh"] = _kept(rec.get("shuyukh")), _kept(rec.get("talamidh"))
    rec["death_year"] = _regex_death_year(source)        # override the LLM's century-naive year (#122)
    tn = _tabaqa_number(source)
    if tn is not None:
        rec["tabaqa"] = tn                               # deterministic طبقة (the LLM sometimes drops it)
    rec["source_text"] = source                          # keep the proof alongside the record
    return rec


def validate_chain(seg: dict, text: str) -> dict | None:
    """Trust an LLM segmentation only if it is **verbatim**: isnād+matn must reconstruct the source
    token-for-token (no word added/lost/changed) and every narrator be a run of the isnād."""
    if not isinstance(seg, dict):
        return None
    isnad, matn = (seg.get("isnad") or "").strip(), (seg.get("matn") or "").strip()
    if not isnad:
        return None
    if _folded_tokens(isnad) + _folded_tokens(matn) != _folded_tokens(text):
        return None                                       # words were added / lost / reordered
    isnad_tokens = set(_folded_tokens(isnad))
    narrators = [n.strip() for n in (seg.get("narrators") or [])
                 if isinstance(n, str) and n.strip() and set(_folded_tokens(n)) <= isnad_tokens]
    if not narrators:
        return None
    return {"isnad": isnad, "matn": matn, "narrators": narrators, "source_text": text}


# ── which chains even need the LLM (the regex handles the clean majority) ──────────────────────
# Matn hints in the FOLDED form (normalize_for_search drops hamza/tashkeel: «جاءت»→«جات», «إنما»→
# «انما») plus story-openers — better to over-flag a few than miss a leak; the LLM + validation
# decide, the regex output is the fallback either way.
_MATN_HINT = re.compile(r"الاعمال|الجنه|النار|الصلاه|رمضان|قوله|تعالي|جات|جاءت|انما|كان رسول|"
                        r"دخل|خرج|سال|اتي|نزلت|فقال|يجاور")


def chain_is_suspicious(text: str) -> bool:
    """A regex-parse worth a second look: no narrators, a verse ﴿…﴾ or a matn word leaked into a
    node, or an over-long terminal node (the matn glued onto the last man)."""
    from app.qa.isnad import analyze_isnad
    names = [n["name"] for n in analyze_isnad(text).narrators]
    if not names:
        return True
    last = names[-1]
    if "﴿" in last or "﴾" in last or len(last.split()) >= 8:
        return True
    return bool(_MATN_HINT.search(normalize_for_search(last)))


# ── prompts (strict: transcribe/segment, never author) ────────────────────────────────────────
RIJAL_PROMPT = """أنت أداةُ استخراجٍ من كتب الرجال. حوِّل الترجمةَ إلى JSON **نقلاً عن النصّ فقط**، بلا اجتهادٍ ولا إضافة.

النص:
«{body}»

أخرِجْ JSON بهذا الشكل فقط (بلا شرح):
{{"name": "اسم الراوي كما في رأس الترجمة",
 "kunya": "كنيته أو null",
 "grade_word": "لفظ الجرح/التعديل كما ورد حرفياً (ثقة، صدوق، الإمام، متروك، كذاب…) أو null إن لم يُذكر",
 "death_year": سنة الوفاة هجرياً عدداً أو null,
 "tabaqa": رقم الطبقة 1..12 أو null,
 "shuyukh": ["من روى عنهم كما كُتبوا"],
 "talamidh": ["من رووا عنه كما كُتبوا"],
 "note": "ملاحظة وجيزة أو null"}}

قواعد صارمة: لا تخترع لفظاً ليس في النص؛ انقل الأسماء كما كُتبت؛ إن لم يُذكر حكمٌ فاجعل grade_word=null."""

CHAIN_PROMPT = """أنت أداةُ فصلِ الإسناد عن المتن وتقطيعِ السند. **لا تُغيّر أيَّ كلمة**؛ انسخ مقاطعَ حرفيةً من النص فقط.

نصّ الحديث كاملاً:
«{text}»

أخرِجْ JSON بهذا الشكل فقط:
{{"isnad": "سلسلة الرواة حرفياً من أول النص حتى نهاية السند",
 "matn": "متن الحديث حرفياً بعد انتهاء السند",
 "narrators": ["كل راوٍ في السند كما كُتب، مرتَّبين من الأعلى إلى الصحابي"]}}

قواعد: isnad+matn يجب أن يساويا النصَّ الأصلي كلمةً بكلمة؛ كلُّ اسمٍ في narrators مقطعٌ حرفيٌّ من isnad؛ لا تُضِفْ ولا تَحذِفْ ولا تُصحِّحْ."""


# ── tarjama / hadith iterators ────────────────────────────────────────────────────────────────
def iter_tarjamas(book_id: int) -> Iterator[tuple[int | None, str]]:
    """(number, body) for each numbered tarjama in a رجال book — the same segmentation the regex
    extractor uses, so the LLM and the regex see exactly the same unit."""
    data = json.loads((BOOKS / f"{book_id}.json").read_text(encoding="utf-8"))
    start = _first_entry_page(data)          # skip the editor's muqaddima (same as the regex extractor)
    pages = [p for p in data.get("pages", []) if start is None or p.get("pg", 0) >= start]
    full = "\n".join(clean_block(p.get("text") or "")
                     for p in sorted(pages, key=lambda p: p.get("pg", 0)))
    bounds = list(_BOUNDARY.finditer(full))
    for i, m in enumerate(bounds):
        if m.group(1) is None:
            continue
        end = bounds[i + 1].start() if i + 1 < len(bounds) else len(full)
        body = re.sub(r"\s+", " ", full[m.end():end]).strip()
        if len(body) >= 4:
            yield arabic_digits_to_int(m.group(1)), body


def iter_chain_texts(book_id: int) -> Iterator[str]:
    from app.parsing.hadith_extract import parse_book_file
    for h in parse_book_file(BOOKS / f"{book_id}.json"):
        if h.text:
            yield h.text


# ── the two passes ────────────────────────────────────────────────────────────────────────────
def _query(llm, prompt: str, cache: Cache, key: str, stats: dict) -> dict:
    """A cached, RESILIENT LLM call: a per-entry error is skipped (that entry falls back to the
    regex) instead of crashing the whole batch; but if the first calls all fail, the engine is down,
    so we abort with a clear message — update.bat's step is non-fatal, and the regex pipeline runs."""
    cached = cache.get(key)
    if cached is not None:
        stats["hit"] += 1                        # reused — no LLM call (this is what makes re-runs cheap)
        return cached
    try:
        out = _parse_json(llm(prompt)) or {}
    except Exception as e:                       # noqa: BLE001 — any provider/transport error
        stats["err"] += 1
        if stats["err"] == 1:
            print(f"  [!] LLM call failed — {type(e).__name__}: {str(e)[:200]}")
        if stats["err"] >= 8 and stats["ok"] == 0:
            sys.exit("[x] LLM engine not responding — is Ollama running with the model pulled "
                     "(`ollama pull <model>`), or the API key set? Aborting the LLM pass; the regex "
                     "pipeline is unaffected.")
        return {}
    stats["ok"] += 1
    cache.put(key, out)
    return out


def run_rijal(books: Iterable[int], llm, cache: Cache, *, sample: int | None, dry: bool, out) -> None:
    n = kept = rejected = 0
    stats = {"ok": 0, "err": 0, "hit": 0}
    for bid in books:
        source = next((k for k, v in RIJAL_BOOKS.items() if v == bid), str(bid))
        taken = 0                                         # --sample is PER BOOK, so it reaches every
        for _num, body in iter_tarjamas(bid):             # book (else it never left the first, تقريب)
            if sample is not None and taken >= sample:
                break
            taken += 1
            n += 1
            prompt = RIJAL_PROMPT.format(body=body)
            if dry:
                if n <= 3:
                    print(f"\n── PROMPT (rijal, {source}) ──\n{prompt}\n")
                continue
            rec = _query(llm, prompt, cache, cache.key("rijal", body), stats)
            good = validate_rijal(rec, body)
            if good:
                kept += 1
                good["source"] = source
                out.write(json.dumps(good, ensure_ascii=False) + "\n")
            else:
                rejected += 1
    tail = " (dry-run)" if dry else f" · {stats['hit']} cached · {stats['ok']} new LLM calls"
    print(f"rijal: {n} tarjamas · kept {kept} · rejected→regex {rejected}{tail}")


def run_chains(books: Iterable[int], llm, cache: Cache, *, sample: int | None, dry: bool, out) -> None:
    seen = sent = fixed = rejected = 0
    stats = {"ok": 0, "err": 0, "hit": 0}
    for bid in books:
        scanned = 0                                       # --sample is PER BOOK (see run_rijal)
        for text in iter_chain_texts(bid):
            if sample is not None and scanned >= sample:
                break
            scanned += 1
            seen += 1
            if not chain_is_suspicious(text):
                continue                                  # the regex parse is fine — skip the LLM
            sent += 1
            prompt = CHAIN_PROMPT.format(text=text)
            if dry:
                if sent <= 3:
                    print(f"\n── PROMPT (chain) ──\n{prompt}\n")
                continue
            seg = _query(llm, prompt, cache, cache.key("chains", text), stats)
            good = validate_chain(seg, text)
            if good:
                fixed += 1
                out.write(json.dumps(good, ensure_ascii=False) + "\n")
            else:
                rejected += 1
    tail = " (dry-run)" if dry else f" · {stats['hit']} cached · {stats['ok']} new LLM calls"
    print(f"chains: scanned {seen} · suspicious→LLM {sent} · re-segmented {fixed} · "
          f"rejected→regex {rejected}{tail}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=("rijal", "chains"), required=True)
    ap.add_argument("--engine", choices=("local", "remote"),
                    help="use the config llm_local_model / llm_remote_model instead of the extraction model")
    ap.add_argument("--model", help="exact model id (e.g. ollama/gemma4:31b-cloud); "
                                    "overrides --engine and the default llm_extract_model")
    ap.add_argument("--book", type=int, action="append", help="restrict to a book id (repeatable)")
    ap.add_argument("--sample", type=int, help="process only the first N units PER BOOK (quick look "
                                               "that still reaches تهذيب الكمال, not just تقريب)")
    ap.add_argument("--dry-run", action="store_true", help="print prompts, never call the LLM")
    ap.add_argument("--out", type=Path, help="output jsonl (default: data/<mode>_llm.jsonl)")
    args = ap.parse_args()

    settings = Settings()
    # Model precedence: --model > --engine (its config brain) > llm_extract_model. The last is the
    # default, so a bare invocation (and update.bat) use the dedicated extraction model — no .env
    # juggling — while --engine / --model stay available for experiments.
    model_name, api_base = _resolve_model(settings, args.engine, args.model)
    books = args.book or list((RIJAL_BOOKS if args.mode == "rijal" else CHAIN_BOOKS).values())
    missing = [b for b in books if not (BOOKS / f"{b}.json").exists()]
    if missing:
        sys.exit(f"missing book(s) {missing} under {BOOKS} — run update.bat to download them first")

    llm = None if args.dry_run else _make_llm(settings, model_name, api_base)
    cache = Cache(model=model_name)                       # keyed by model → switching models re-extracts
    out_path = args.out or Path(f"data/{args.mode}_llm.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not args.dry_run:
        print(f"model={model_name} · books={books} · out={out_path}  (cache: {CACHE_DB})")
    with (open(os.devnull, "w") if args.dry_run else open(out_path, "w", encoding="utf-8")) as out:
        runner = run_rijal if args.mode == "rijal" else run_chains
        runner(books, llm, cache, sample=args.sample, dry=args.dry_run, out=out)


if __name__ == "__main__":
    main()
