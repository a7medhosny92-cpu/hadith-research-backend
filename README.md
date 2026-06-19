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
turath.io
   │  [1] Ingestion   app/ingestion/   polite · rate-limited · resumable
   ▼
data/raw/turath/*.json
   │  [2] Parsing     app/parsing/     HTML → متن · إسناد · grade · شرح · citation
   ▼
data/processed/*.jsonl
   │  [3] Indexing    scripts/         index · embed · build_graph · build_rijal · audit
   ▼
 ┌── Local indexes (sqlite; PostgreSQL + pgvector in production) ──────────────────┐
 │  FTS5 hadith · FTS5 شروح · dense vectors · narrator graph · documented network  │
 │  canonical rijal base (~21k narrators, no doublings) + self-audits              │
 └──────────────────────────────────────────────────────────────────────────────────┘
   │  [4] Retrieval   app/search/      lexical · semantic · hybrid (RRF fusion)
   │  [5] Sciences    app/qa/ · app/rijal/
   │        answer (RAG) · takhrij (صيغ · صحابي · أخرجه) · isnad verdict (الحكم على الإسناد)
   │        rijal identification (تمييز المهمل: قواعد بالشيخ · network · prominence)
   │        self-audits (التدقيق · تدقيق المتون · تعارض الرجال) · علّة/شذوذ hints
   │  [6] LLM engine  app/qa/llm.py    off / local (Ollama) / remote (Claude) — via LiteLLM
   ▼                  (also build-time FAITHFUL extraction: scripts.build_rijal_llm)
 [7] FastAPI  app/main.py   →  /search · /hadith · /ask · /takhrij · /verify-isnad
        │              /narrator · /narrators · /books · /sharh-books · /notebook
        │              /audit · /matn-audit · /conflicts · /coverage · /sources
        └─ /app  →  static single-file RTL UI ⟷ native desktop window.  Tabs:
            action  بحث · سؤال · تخريج · راوٍ · الإسناد · الشبكة · الكتب · الرواة · دفتري
            study   التدقيق · تدقيق المتون · تعارض الرجال · المنهجية · البنية · التقنية
```

The chain is the same everywhere: the system **retrieves and cites**, it never
invents — every answer stays verifiable against the real sources.

The **LLM engine is provider-agnostic** (via LiteLLM) and chosen per request via
`?engine=`: `local` is Ollama, `remote` is **any** cloud provider. Pick the exact
model per request with `?model=` (e.g. `anthropic/claude-sonnet-4-6`, `openai/gpt-4o`,
`gemini/gemini-2.0-flash`, `groq/…`, `ollama/llama3`) or default with
`LLM_REMOTE_MODEL`; set the matching `*_API_KEY` in `.env`. No code changes to swap
brains or providers.

## What it does

| Capability | Endpoint | State |
|---|---|---|
| Ingestion from turath.io (resumable, rate-limited) | — | ✅ |
| Parsing → structured متن / إسناد / grade / citation + شروح (multi-edition) | — | ✅ |
| **Search** — lexical FTS (uncapped) · semantic · **hybrid (RRF)** | `/search?mode=` | ✅ |
| **Ask (RAG)** — top hadith + **full شرح** + **rulings (أحكام)**, cited; LLM switch off/local/remote | `/ask?engine=` | ✅ |
| **Takhrij** — *every* narration → variants (صيغ: بلفظه/بنحوه/بمعناه) · grouped by **Companion** · «أخرجه» · chains shown | `/takhrij` | ✅ |
| **Isnad** — structure (سماع/عنعنة/تحويل), **narrator identification** (تمييز المهمل: a homonym is fixed by his شيخ via curated قواعد, the documented network, الرفقة, then prominence), per-narrator grade, **continuity (اتصال)**, and a single bottom-line **verdict «الحكم على الإسناد»** (rijal + اتصال + عنعنة, with disclaimer) | `/verify-isnad` | ✅ |
| **Narrator base & network (علم الرجال)** — a **canonical base, one record per man, no doublings** (~21k narrators: تقريب + الكاشف authority, folded with الإصابة · الثقات · لسان · سير coverage, deduped by `dedup.collapse_duplicates`); شيوخ/تلاميذ from the chains, weighted; built by `scripts.build_rijal` (+ optional faithful LLM extraction) | `/narrator` · `/narrators` | ✅ |
| **Library navigator (الكتب)** — browse the corpus structurally: collections → their كتب/أبواب → the hadiths under each, with «كتاب ← باب» nesting and per-book search; شروح browsable too | `/books` · `/sharh-books` | ✅ |
| **Self-audits** — the system rescans its own output: **«التدقيق»** flags suspect isnad verdicts (متروك/كذاب/صحابي-mid-chain/مشترك), **«تدقيق المتون»** flags suspect texts, **«تعارض الرجال»** catches a grave-vs-trustworthy name collision | `/audit` · `/matn-audit` · `/conflicts` | ✅ |
| **Coverage report** — how much of the chains the base covers (identified · مشترك · uncovered), weighted by chain position | `/coverage` | ✅ |
| **Scholars' rulings (أحكام)** — ordered by طبقة, divergence flagged, «حسن صحيح» resolved by the number of chains; structural **علّة/شذوذ hints** on the gathered طرق | in `/ask`,`/takhrij` | ✅ |
| Scholars' explanations (شروح) linked per hadith & quoted with attribution | in `/ask` | ✅ |
| **Study notebook (دفتري)** — save any hadith / narrator / answer / isnad with a note; persists across rebuilds | `/notebook` | ✅ |
| **Reference pages** — in-app, kept in sync with the code: **المنهجية** (every datum: its source, derivation, advantages, limits), **البنية** (how the app is built), **التقنية** (the exact implementation: modules, scripts, data files, endpoints) | in `/app` | ✅ |

**Dev vs production.** Everything above runs **today** on your machine with a light
stack: parsing is pure-stdlib and the indexes are **sqlite** — FTS5 for lexical
search (Arabic-folded), plus local dense **vectors** and the **narrator graph**.
The storage interface is backend-agnostic, so production swaps in **PostgreSQL +
pgvector** (hybrid lexical+semantic) and an **LLM** for `/ask` synthesis by
installing the optional extras and flipping the engine on (`LLM_DEFAULT_ENGINE=
local|remote`, or per request `/ask?engine=…`) — no caller changes. The ORM models,
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
python -m scripts.update --semantic   # also build the semantic index (smart search)
```

On Windows, **double-click `update-semantic.bat`** to update *and* turn on semantic
search in one go (first run downloads a model + embeds the corpus — one-off).

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
| `GET /search?q=…` | rank hadith by relevance (Arabic-folded; `field=all\|matn\|isnad`, filter by `collection`/`grade`; `mode=lexical\|semantic\|hybrid`) |
| `GET /hadith/{id}` | a single hadith with its citation |
| `GET /ask?q=…` | the most relevant hadith + grade + the **scholars' شرح**, the **scholars' rulings (أحكام)** on it ordered by era (صحّحه/ضعّفه…, divergence surfaced), cited (add `&engine=local\|remote` and optionally `&model=<any litellm id>` to synthesise with an LLM) |
| `GET /takhrij?hadith_id=…` (or `q=…`) | **every** narration of the same report (lexical+semantic recall), grouped **by Companion (الصحابي)** then into distinct wordings (صيغ) labelled بلفظه/بنحوه/بمعناه — each Companion with an «أخرجه» summary, every chain shown |
| `GET /verify-isnad?hadith_id=…` (or `isnad=…`) | parse the **chain of narrators**, flag سماع/عنعنة/تحويل, **grade each narrator** (رجال), check each link's **continuity (اتصال)** against the narrator network, and return a single bottom-line **verdict «الحكم على الإسناد»** that fuses the weakest-link grade + الاتصال + عنعنة (a study verdict on the apparent state of the men, not a full تصحيح — needs النظر في العلّة والشذوذ) |
| `GET /narrator?name=…` | a narrator's place in the network (شبكة الرواة): his **شيوخ** (narrates from) and **تلاميذ** (narrate from him), weighted, plus his grade and the critics' أقوال الأئمة |
| `GET /narrators?letter=&grade=&q=` | **browse all narrators (الرواة)** — paged, with letter + درجة facets (powers the in-app browse tab) |
| `GET /books` · `/books/{id}/chapters` · `/books/{id}/hadiths` | **library navigator (الكتب)** — collections → كتب/أبواب → the hadiths under each; `/sharh-books*` browses the commentaries |
| `GET /audit` · `/matn-audit` · `/conflicts` | the **self-audits**: suspect isnad verdicts (التدقيق), suspect texts (تدقيق المتون), grave-vs-trustworthy name collisions (تعارض الرجال) — each example opens the case |
| `GET /coverage` | how much of the chains the رجال base **covers** (identified · مشترك · uncovered), weighted by chain position |
| `GET/POST/PATCH/DELETE /notebook` | your **study notebook (دفتري)**: save a hadith / narrator / answer / isnad with a personal note + tags, search them, edit, delete — stored in `data/notebook.db`, **never touched by index rebuilds** |
| `GET /sources` | the books the app draws on (collections · شروح · rijal) with their **editions** (read from the downloaded files) — powers the books list on the «المنهجية» page |

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

It opens a window over the local app to **search**, **ask**, trace **takhrij**, and
explore a **narrator (راوٍ)**. Search/takhrij return *all* matches (revealed in batches,
no cap), `/ask` shows the **complete** شرح passage. In «ask» a dropdown switches the
engine **off / local / remote** live, a model box picks **any** litellm model, and
**«قارن النماذج»** runs the question across the local Qwen sizes (3b · 7b · 14b)
**side by side with timings**, so you can see which size answers best for you.

**Semantic ("smart") search.** Beyond exact words, you can match by *meaning*
(synonyms, paraphrase). Build a local vector index once, then `/ask` retrieves with a
lexical+semantic **hybrid** automatically, and `/search?mode=semantic|hybrid` is available:

```bash
pip install -e ".[embeddings]"   # sentence-transformers + torch (CPU is fine)
python -m scripts.embed          # embeds the corpus → data/vectors.db (one-off)
# or in one go on update:  python -m scripts.update --semantic
```

For production search/answers, install the extras and load PostgreSQL:

```bash
pip install -e ".[embeddings,llm]"
python -m scripts.load_db        # JSONL → Postgres + pgvector (embeds matn & شروح)
# pick a brain: LLM_DEFAULT_ENGINE=local (Ollama) or remote (Claude, + API key),
# or per request /ask?engine=local|remote  ('off', the default, stays extractive)
```

**Narrator gradings (رجال) & the chain verdict.** `/verify-isnad` grades each narrator
using a curated, attributed seed (`app/rijal/seed.jsonl`, verdicts from تقريب التهذيب;
the Companions are عدول by consensus), then rolls everything into one bottom-line
**«الحكم على الإسناد»**: it takes the *weakest-link* grade, lets a clear **انقطاع**
(an unseen link in the network) override an otherwise sound chain, and holds back a
firm تصحيح when there is **عنعنة** or when narrators are still unknown to the base.
It is deliberately conservative — a study verdict on the *apparent* state of the men
and the connection, **not a full تصحيح** (which also needs النظر في العلّة والشذوذ) and
not a fatwa.

**The canonical narrator base (~21k men, no doublings).** Quality scales with how many
narrators are graded *and* with identifying the right man. `scripts.build_rijal` builds
**one record per narrator** from **تقريب التهذيب** (Ibn Ḥajar — the terse authority over the
Six Books) + **الكاشف** (al-Dhahabī, second opinion), then folds in coverage sources only to
*fill gaps*, never to duplicate a man: **الإصابة** (Companions), **الثقات** (men outside the
Six Books), **لسان الميزان** (the criticised), **سير أعلام النبلاء** (later narrators), plus
the multi-critic **أقوال الأئمة** from **تهذيب الكمال / الجرح والتعديل**. A dedup engine
(`app/rijal/dedup.py`) collapses the same man written two ways (تقريب↔الكاشف, a كنية vs an
ism-led name, a deep-lineage نسب match) under طبقة/grade guards — so the base carries **no
false «مشترك»**. It writes `data/rijal.jsonl`, which `/verify-isnad` **auto-loads on the next
start**. It runs as the last steps of `scripts.update` / `update.bat` (build_graph → build_rijal
→ audit), or on its own:

```bash
python -m scripts.build_rijal                       # build/refresh data/rijal.jsonl
python -m scripts.build_rijal --input narrators.jsonl   # merge a hand-made JSONL too
python -m scripts.build_rijal_llm --mode rijal|chains   # optional FAITHFUL LLM extraction
# read-only diagnostics: scripts.audit_isnad · audit_coverage · probe_name · peek_name_chains
```

**Identifying the man, not just grading a name (تمييز المهمل).** A chain rarely spells a
narrator out, so the verdict identifies him **from the chain before grading**: a homonym is
fixed by his **شيخ** through curated **قواعد** («سفيان عن الأعمش» = الثوري), the **documented
شيخ→تلميذ network** (تهذيب/الجرح/الثقات), the surrounding **company (الرفقة)**, then a
**prominence** prior — and when the text genuinely cannot decide, the node is **held «مشترك»,
never guessed** (لا نختلق). The whole corpus is then **re-audited** (`/audit`, `/conflicts`,
`/coverage`) so every improvement is measured.

## Data source, attribution & ethics

Content is sourced from **[turath.io](https://app.turath.io/)**. The classical
texts themselves are public domain, but the digital library is the result of
their effort, so this project crawls **politely** (an honest User-Agent, a modest
rate limit, full resumability and local caching) and **attributes the source**.
You are responsible for complying with turath.io's terms; for bulk/commercial use,
consider contacting the maintainers.

This is a **study aid** that surfaces verifiable citations — it is not a substitute
for qualified scholarship or a source of religious rulings (fatwā).
