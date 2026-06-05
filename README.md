# review-backend — بحث وتحقيق الحديث

Backend for **searching, studying and verifying ḥadīth** (the sayings of the
Prophet Muḥammad ﷺ) entirely in **Classical Arabic (الفصحى)**, built as a
Retrieval-Augmented Generation (RAG) system over the
[turath.io](https://app.turath.io/) heritage library.

The model never *invents* ḥadīth: it **retrieves** them from the real sources,
**cites** them (book / volume / page / number / grade), and reasons over them —
because in this domain a wrong attribution is a serious error.

Each answer is meant to surface, for a hadith:

* the **متن** (text, fully vocalised) and its **إسناد** (chain of narrators),
* the authenticity **grade** (صحيح / حسن / ضعيف …) and **takhrij** (other sources),
* and the **explanations of the scholars (شروح الحديث)** — e.g. Fatḥ al-Bārī,
  Sharḥ al-Nawawī, Tuḥfat al-Aḥwadhī — quoted **with attribution** to the commentator.

> _Applicazione per approfondire, studiare e verificare gli hadith in arabo classico,
> con le spiegazioni dei sapienti (شروح)._

## Architecture (7 layers)

```
turath.io ─▶ [1] Ingestion ─▶ [2] Parsing ─▶ [3] Store ─▶ [4] Indexing
            (resumable,       (HTML → matn/  (Postgres   (Arabic embeddings
             rate-limited)     isnad/grade)   + pgvector)  + lexical search)
                                                                  │
   [7] FastAPI ◀─ [6] LLM engine ◀─ [5] Retrieval (RAG)  ◀────────┘
   /search /ask    (provider-agnostic:  (hybrid dense + lexical,
   /takhrij        local Ollama + Claude  rerank, grounded citations)
   /verify-isnad    + OpenAI + …)
```

The **LLM engine is provider-agnostic**: the default is a local model via Ollama,
but any cloud engine (Claude, OpenAI, …) works by changing `LLM_MODEL` and
providing an API key — no code changes.

## Status

| Phase | What | State |
|------|------|-------|
| 0 | Scaffold, config, FastAPI app, CI/tests | ✅ done |
| 1 | turath.io ingestion (catalog, client, resumable downloader) | ✅ done |
| 2 | Parsing → structured matn / isnad / grade / citation | ✅ done |
| 3 | Enrichment (grade / takhrij / rijal from open datasets) | ☐ |
| 4 | Embeddings + hybrid search (`/search`) | ☐ |
| 5 | RAG `/ask` (Classical-Arabic, cited) | ☐ |
| 6 | **Scholars' explanations (شروح)** linked to hadith & surfaced in answers | ☐ |
| 7 | Verification (`/takhrij`, `/verify-isnad`) | ☐ |

## Corpus scope

Only the **ḥadīth-sciences categories** of turath.io are ingested (configurable in
`app/config.py`). Confirmed live against `files.turath.io/data-v3.json`:

| cat_id | category | books |
|---|---|---|
| 6 | كتب السنة (collections) | 1241 |
| 7 | شروح الحديث (commentaries) | 265 |
| 8 | التخريج والأطراف (takhrij) | 129 |
| 9 | العلل والسؤلات (defects) | 78 |
| 10 | علوم الحديث (methodology) | 320 |
| 26 | التراجم والطبقات (narrators / rijāl) | 579 |

That is ~2,612 books / ~2.9M pages, so downloading is **prioritised and resumable**:
a curated set of canonical collections (Bukhārī, Muslim, the Sunan, …) is seeded
first to get a useful system fast.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # add ",embeddings,llm" when working on search/RAG
cp .env.example .env

# run the API
uvicorn app.main:app --reload    # http://localhost:8000/docs

# run the tests
pytest

# (optional) Postgres + Ollama for later phases
docker compose up -d db ollama
```

### Ingestion (downloading from turath.io)

```bash
python -m scripts.ingest --list-categories          # inspect scope, no download
python -m scripts.ingest --books 1284 --limit-pages 3   # smoke test (3 pages of Bukhārī)
python -m scripts.ingest --priority                 # seed the canonical collections
python -m scripts.ingest --priority --with-commentaries  # + their شروح (Fatḥ al-Bārī …)
python -m scripts.ingest --categories 6 7 8 9 10 26 # full hadith crawl (long, resumable)
```

**Scholars' explanations (شروح).** The commentaries live in turath category 7 and are
already in scope. A curated map of each collection → its major commentaries (Fatḥ
al-Bārī & ʿUmdat al-Qārī for Bukhārī, Sharḥ al-Nawawī for Muslim, Tuḥfat al-Aḥwadhī
for Tirmidhī, ʿAwn al-Maʿbūd for Abū Dāwūd, …) lives in `app/ingestion/catalog.py`
(`COMMENTARIES`). They are linked to each hadith and quoted — with attribution — in the
answer (phase 6).

Progress is tracked in `data/raw/turath/manifest.json`; rerun to resume. Live
status is also exposed at `GET /health/ingestion`. Downloaded data lives under
`data/` and is **not** committed.

## Data source, attribution & ethics

Content is sourced from **[turath.io](https://app.turath.io/)**. The classical
texts themselves are public domain, but the digital library is the result of
their effort, so this project crawls **politely** (an honest User-Agent, a modest
rate limit, full resumability and local caching) and **attributes the source**.
You are responsible for complying with turath.io's terms; for bulk/commercial use,
consider contacting the maintainers.

This is a **study aid** that surfaces verifiable citations — it is not a substitute
for qualified scholarship or a source of religious rulings (fatwā).
