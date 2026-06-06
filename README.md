# hadith-research-backend — بحث وتحقيق الحديث

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

The **LLM engine is provider-agnostic** and chosen per request via `?engine=`:
`local` is a model via Ollama, `remote` is any cloud engine (Claude, OpenAI, …) —
set `LLM_REMOTE_MODEL` + an API key. No code changes to swap brains.

## Status

| Phase | What | State |
|------|------|-------|
| 0 | Scaffold, config, FastAPI app, CI/tests | ✅ done |
| 1 | turath.io ingestion (catalog, client, resumable downloader) | ✅ done |
| 2 | Parsing → structured matn / isnad / grade / citation (multi-edition) | ✅ done |
| 3 | Enrichment | ◐ takhrij ✅ · rijal gradings (curated seed) ✅ · full رجال DB ☐ |
| 4 | Search (`/search`, `/hadith/{id}`) | ✅ lexical FTS · semantic (pgvector) scaffolded |
| 5 | `/ask` (Classical-Arabic, cited) | ✅ extractive · **local/remote LLM switch** (`?engine=`) |
| 6 | **Scholars' explanations (شروح)** linked to hadith & surfaced in answers | ✅ done |
| 7 | Verification (`/takhrij`, `/verify-isnad`) | ✅ done |

**Dev vs production.** Everything above runs **today** on a zero-extra-deps stack:
parsing is pure-stdlib and search is **sqlite FTS5** (Arabic-folded). The search
interface is storage-agnostic, so production swaps in **PostgreSQL + pgvector**
(hybrid lexical+semantic) and an **LLM** for `/ask` synthesis by installing the
optional extras and flipping the LLM engine on (`LLM_DEFAULT_ENGINE=local|remote`,
or per request `/ask?engine=…`) — no caller changes. The ORM models,
DB loader and embedding/LLM hooks are in place (`app/models`, `scripts/load_db.py`,
`app/search/embeddings.py`, `app/qa/llm.py`).

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

### Get the corpus locally — one command

On **your own machine** (where the data persists), download + parse + index in one go:

```bash
bash scripts/setup_local.sh          # canonical: core collections + main شروح (default)
bash scripts/setup_local.sh core     # collections only — lighter/faster
bash scripts/setup_local.sh full     # every hadith-sciences category (~2.9M pages — days)
```

It is **resumable**: if it stops, run it again and it continues. The steps below are
the same pipeline run by hand (ingest → parse → index).

### Keep it up to date

Pull the latest code and refresh the corpus in one go — on Windows just **double-click
`update.bat`**:

```bash
python -m scripts.update              # code + corpus
python -m scripts.update --code-only  # just code + dependencies (fast)
```

Safe to re-run anytime: `git pull` is fast-forward, the crawl resumes, and
parse/index are idempotent.

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

### Build the searchable corpus, then query it

```bash
python -m scripts.parse      # raw pages → structured JSONL (hadith + شروح, multi-edition)
python -m scripts.index      # build the sqlite FTS indexes (data/index.db, data/sharh_index.db)
uvicorn app.main:app --reload
```

| Endpoint | What it does |
|---|---|
| `GET /search?q=…` | rank hadith by relevance (Arabic-folded; `field=all\|matn\|isnad`, filter by `collection`/`grade`) |
| `GET /hadith/{id}` | a single hadith with its citation |
| `GET /ask?q=…` | the most relevant hadith + grade + the **scholars' شرح** on that exact hadith, cited (add `&engine=local` or `&engine=remote` to synthesise with an LLM) |
| `GET /takhrij?hadith_id=…` (or `q=…`) | the hadith's **parallel narrations** across collections |
| `GET /verify-isnad?hadith_id=…` (or `isnad=…`) | parse the **chain of narrators**, flag سماع/عنعنة/تحويل, and **grade each narrator** (رجال) with a weakest-link verdict |

```bash
# examples
curl 'localhost:8000/search?q=إنما الأعمال بالنيات'
curl 'localhost:8000/ask?q=فضل تعلم القرآن'
curl 'localhost:8000/takhrij?q=من كذب علي متعمدا'
```

### Desktop app (a native window)

Prefer an app window over the browser? A simple **native OS window** (Arabic renders
correctly — the same UI is also at `http://localhost:8000/app` in any browser):

```bash
pip install -e ".[desktop]"
python -m app.desktop            # or the console script:  hadith-app
```

It opens a window over the local app to **search**, **ask**, and trace **takhrij**.

For production search/answers, install the extras and load PostgreSQL:

```bash
pip install -e ".[embeddings,llm]"
python -m scripts.load_db        # JSONL → Postgres + pgvector (embeds matn & شروح)
# pick a brain: LLM_DEFAULT_ENGINE=local (Ollama) or remote (Claude, + API key),
# or per request /ask?engine=local|remote  ('off', the default, stays extractive)
```

**Narrator gradings (رجال).** `/verify-isnad` grades each narrator using a curated,
attributed seed (`app/rijal/seed.jsonl`, verdicts from تقريب التهذيب; the Companions
are عدول by consensus). The verdict is structural — a *weakest-link* read of the
chain — and explicitly not a full تصحيح (which also needs اتصال and absence of علة/شذوذ).
To grade more narrators, build a fuller رجال JSONL and point `RIJAL_PATH` at it:

```bash
python -m scripts.build_rijal --input narrators.jsonl --output data/rijal.jsonl
```

## Data source, attribution & ethics

Content is sourced from **[turath.io](https://app.turath.io/)**. The classical
texts themselves are public domain, but the digital library is the result of
their effort, so this project crawls **politely** (an honest User-Agent, a modest
rate limit, full resumability and local caching) and **attributes the source**.
You are responsible for complying with turath.io's terms; for bulk/commercial use,
consider contacting the maintainers.

This is a **study aid** that surfaces verifiable citations — it is not a substitute
for qualified scholarship or a source of religious rulings (fatwā).
