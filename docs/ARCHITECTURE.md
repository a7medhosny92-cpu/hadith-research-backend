# ARCHITECTURE — how the Hadith research backend is built

A consolidated, code-accurate map of the whole system: what each subsystem does, how data
flows end-to-end, and the load-bearing design decisions. Written to be the durable reference
so a reader (or a future session) does not re-derive the system or work from stale memory.

![System overview — the build pipeline, the canonical رجال base (dedup engine + what one record
accumulates), the verdict-time resolution ladder سُلّم التمييز, and the API/UI surface](architecture.png)

> *Figure: the four bands of the system. Regenerate after a structural change with
> `python docs/architecture_diagram.py` (the figure is its committed output — keep them in step).*

> **Scope & freshness.** Reflects the tree as of the **canonical-base** work (June 2026): one رجال
> record per man (`collapse_duplicates`: `same_man` + prefix-extension + deep-lineage نسب +
> kunya/ibn shadow → ~19.6k narrators, removable ~1), the الإصابة/الثقات/لسان coverage sources, the
> named أقوال الأئمة, and the joint resolver. Line references (`file:line`) are anchors that drift
> across edits — trust the function/symbol name over the number. For *forward* plans see
> `docs/ROADMAP.md`; for the one-time code audit see `docs/AUDIT.md`; for the تهذيب الكمال extractor
> study see `docs/TAHDHIB.md`; for live worklog and conventions see `CLAUDE.md`. This file documents
> the system **as it is**.

## Table of contents
1. [Overview & guarantees](#1-overview--guarantees)
2. [Build pipeline (the 8 steps)](#2-build-pipeline-the-8-steps)
3. [Data files & contracts](#3-data-files--contracts)
4. [Parsing & extraction](#4-parsing--extraction)
5. [The رجال identification core](#5-the-رجال-identification-core)
6. [Isnād verification & QA](#6-isnād-verification--qa)
7. [Search engine](#7-search-engine)
8. [HTTP API & app skeleton](#8-http-api--app-skeleton)
9. [The UI](#9-the-ui)
10. [The self-audit «التدقيق»](#10-the-self-audit-التدقيق)
11. [Identity-resolution strategy & current state](#11-identity-resolution-strategy--current-state)
12. [Conventions & how to run](#12-conventions--how-to-run)

---

## 1. Overview & guarantees

A local-first **RAG backend for studying ḥadīth in Classical Arabic** over the turath.io
library: lexical + semantic **search**, cited **Q&A**, **takhrīj** (parallel narrations), and
**isnād verification** with narrator (رجال) gradings.

- **Core guarantee:** the system never invents ḥadīth. It *retrieves* them from the real
  sources, *cites* them (collection / volume / page / number / grade), and *reasons* over them.
  Transmitted data is authoritative; analytical data (verdicts) is always reviewable and
  surfaces its sources.
- **Local-first, CPU-only, single-user.** Stack: **FastAPI + SQLite** (FTS5 + float32 vector
  blobs) + optional **sentence-transformers**; desktop window via **pywebview**; a single-file
  vanilla-JS/SVG UI at `app/static/index.html`. No ML dependency is required to run — everything
  degrades to a working baseline.
- **Two backends behind one interface.** The live path is the sqlite dev backend. A
  PostgreSQL + pgvector production path is *scaffolded but unwired* (`app/db.py`,
  `app/models/tables.py`, `scripts/load_db.py`) — `ROADMAP.md` item 9, low priority while local.

**Design philosophy (the throughline).** Identifying *which* historical narrator a chain means
(تمييز المهمل) is the central problem, and the guiding rule is **identify from the chain, and
when identity isn't certain, refuse to grade rather than guess**. A grade tells you *how good* a
man is, not *which* man he is — so ambiguity is resolved by **identity data from the chain**, not
by the grade. See [§11](#11-identity-resolution-strategy--current-state) for the full strategy;
it is the intellectual core of the رجال subsystem.

**Repo layout (≈8,200 LOC Python + one big HTML UI):**

| Area | Path | Role |
|---|---|---|
| Ingestion | `app/ingestion/` | polite, resumable turath.io crawler |
| Parsing | `app/parsing/` | raw page text → structured ḥadīth / رجال / grades |
| Search | `app/search/` | FTS5 lexical + dense vectors + hybrid fusion |
| Rijal | `app/rijal/` | narrator index, graph, canon, dedup, muhmal, grades |
| QA | `app/qa/` | isnad, takhrij, rulings, answer, dossier, llm, intent |
| Routers | `app/routers/` | the 10 FastAPI endpoints |
| Scripts | `scripts/` | the build pipeline + diagnostics |
| UI | `app/static/index.html` | single-file RTL Arabic UI |
| Docs | `docs/`, `CLAUDE.md`, `README.md` | plans, audit, worklog |

---

## 2. Build pipeline (the 8 steps)

`update.bat` → `python -m scripts.update` is an **8-step pipeline**, orchestrated by
`scripts/update.py`. `step()` runs each as a subprocess and **halts hard** (`sys.exit(1)`) on the
first failure — no silent continuation.

| # | Step | Module | Rebuild kind | Writes |
|---|---|---|---|---|
| 1 | `git checkout main` | — | — | (realigns the checkout) |
| 2 | `git pull --ff-only` | — | — | fast-forward only |
| 3 | refresh deps | pip | — | `.[dev,desktop,llm(,embeddings)]` |
| 4 | download books | `scripts.ingest` | **incremental / resumable** | `data/raw/turath/...` |
| 5 | parse | `scripts.parse` | **full** (idempotent) | `data/processed/*.jsonl` |
| 6 | index | `scripts.index` | **full** | `index.db`, `sharh_index.db` |
| 7 | build graph | `scripts.build_graph` | **full** | `narrators.db`, `muhmal.json`, `documented_network.json` |
| 8 | build rijal | `scripts.build_rijal` | **full** | `rijal.jsonl` |
| + | embed *(conditional)* | `scripts.embed` | **incremental** | `vectors.db`, `embed_cache.db` |
| + | audit *(always last)* | `scripts.audit_isnad` | **full** | `audit.json` |

Key facts (verified in `scripts/update.py`):

- **Only download and embed are incremental.** Parse, index, build_graph, build_rijal and audit
  fully rebuild every run — so a code fix to extraction/matching takes effect on the next
  `update.bat` **even with zero new downloads**.
- **`--code-only` is a footgun:** it returns right after step 3 (pull + deps) — *no* rijal /
  graph / audit rebuild. Don't expect fresh audit numbers from it.
- **Auto-semantic.** `semantic = args.semantic or vector_index_path.exists()` — once
  `data/vectors.db` exists, every update re-embeds (incrementally) to keep row-ids aligned.
- **`--full`** downloads all hadith-science categories (`6 7 8 9 10 26`) instead of the default
  `--priority --with-commentaries`.
- **Atomicity.** index/graph/embed build through `scripts/_atomic.rebuild()`: build into
  `*.tmp` → `count()` → `os.replace(tmp, target)`. On a Windows file-lock (DB open in the running
  app) it raises a clean "close the app" `SystemExit`, not a traceback.

> **⚠ The one-iteration graph/rijal lag (by design).** `build_graph` is **step 7**, `build_rijal`
> is **step 8**. So `build_rijal`'s dedup and the final audit read the **previous run's**
> `narrators.db` (the graph isn't rebuilt with the new rijal until next time). `rijal.jsonl` ↔
> `narrators.db` are therefore always one iteration out of phase. **Practical consequence:** to
> see the *full* effect of a رجال-identity change (e.g. #109/#110) on the audit, it can take
> **two `update.bat` runs**. A stall mid-`build_graph` leaves `data/_chains.tmp.jsonl` behind and
> a stale `audit.json` (audit is the very last step) — just re-run; it resumes.

---

## 3. Data files & contracts

Everything lives under `data/` (gitignored; wiped on a fresh container). Paths come from
`app/config.py` `Settings`.

| File | Producer | Consumer | Format / notes |
|---|---|---|---|
| `raw/turath/catalog.json` | ingest | catalog | the turath `data-v3.json` (cats/books/authors) |
| `raw/turath/manifest.json` | downloader | downloader, `/health/ingestion` | resume state per book |
| `raw/turath/books/{id}.json` | downloader | parsers | `{meta, indexes, pages:[{pg, meta, text}]}` |
| `processed/{id}.jsonl` | parse | index, build_graph | one ḥadīth per line |
| `processed/sharh/{id}.jsonl` | parse | index | one شرح passage per line |
| `index.db` | index | search, audit | FTS5 `hadith` |
| `sharh_index.db` | index | answer/dossier | FTS5 `sharh` |
| `narrators.db` | build_graph | canon, dedup, audit, `/narrator` | graph `narrator`+`link` |
| `muhmal.json` | build_graph | isnad/audit/verify | `(تلميذ,شيخ)` → full name |
| `documented_network.json` | build_graph | resolve, audit/verify | `{"students": {شيخ-key → [تلميذ-keys]}}` (تهذيب/الجرح/الثقات) |
| `rijal.jsonl` | build_rijal | RijalIndex everywhere | one narrator record per line |
| `vectors.db` | embed | hybrid/takhrij | id→float32 blob (≈346 MB live) |
| `embed_cache.db` | embed | embed | content-keyed vector cache |
| `audit.json` | audit | UI «التدقيق» tab | `{counts, cases}` |
| `notebook.db` | runtime | `/notebook` | **never rebuilt** (survives updates) |

Two cross-cutting contracts:

- **Shared id between `index.db` and `vectors.db`.** Both are built from the same JSONL rows in
  the same order; `HadithIndex.iter_for_embedding()` yields `(rowid, "matn chapter")` in rowid
  order. A semantic hit's id resolves straight back to a full ḥadīth record. (A re-index reassigns
  ids, which is why embed re-runs — but the cache is keyed by *content*, so unchanged matns are
  reused.)
- **Per-volume page numbering.** The turath `/page` endpoint numbers pages **per printed volume**,
  resetting `pg` to 1 each volume, carrying the volume in `meta`. So a citation needs **`vol` +
  `page`**, never `page` alone (تهذيب has 35 volumes; al-Mustadrak's printed «204» recurs 35×).
  The downloader stores `meta` verbatim; `volume` flows through parse → index (UNINDEXED column)
  → the UI's `citeOf()` (« · ج V · ص P»). **Keep this for any new citation surface.**

---

## 4. Parsing & extraction (`app/parsing/`)

Turns raw turath book JSON into structured ḥadīth, isnād/matn splits, narrator records and grades.
Routing in `scripts/parse.py`: رجال source books (`RIJAL_SOURCES = {8609, 2171}`) and prose رجال
(`RIJAL_PROSE_BOOKS = {3722, 2170, 1278, 1293}`) are **skipped** (handled by build_rijal /
build_graph); commentary (cat 7) → `parse_sharh_file`; everything else → `parse_book_file`, with
`default_grade` from `SAHIH_BY_DEFAULT = {1284, 1727}` (Bukhārī/Muslim).

**Foundational folding (`normalize.py`)** — the lowest layer everything depends on:
- `normalize_for_search` = strip tashkeel/tatweel → fold letters (`أإآٱ→ا`, `ى→ي`, `ؤ→و`,
  `ئ→ي`, drop `ء`, **`ة→ه`**) → drop non-Arabic → collapse whitespace. LRU-cached `1<<17`.
- `fold_kunya` unifies **أبو/أبا/أبي → «ابو»**, with one **critical exception**: «أبي» right
  before «بن» stays — it's the *name* أُبَيّ (أُبَيّ بن كعب), not a kunya.
- `NEGATORS = {غير, ليس, لست, لسنا, لم, لن}` — note **لا/ما are deliberately excluded** (they appear
  in positive idioms like «لا بأس به»). `negated_before` cancels a following verdict.

**Diacritic tolerance (`html_clean.py`)** — `flexible_word(word)` inserts an optional
combining-marks class between every character so a regex matches vocalised text («روى عن» ↦
«رَوَى عَن»). The marks class is built from explicit codepoint ranges so it can *never* swallow
the letter block. `clean_block` preserves line breaks (markers are line-anchored); `clean_body`
collapses everything (used for شرح).

**`isnad_matn.split_isnad_matn(text) → (isnad, matn, confidence)`** — splits one ḥadīth where no
markup separates chain from text. A **6-strategy cascade** (confidence ∈ `quote | phrase |
matn-only | none`):
1. **quote** (strongest): matn = first quoted span, **extended across the narration *between*
   dialogue quotes of one story** — stop only at an editorial/takhrīj marker (`_EDITORIAL`:
   أخرجه/رواه/قلت/على شرط/هذا حديث/…) **or** a gap `> 220` chars (`_MAX_NARRATION_GAP`). Then
   `_story_start` repositions the matn back to the «أنّ» when the first quote sits inside a
   post-chain story (`_ANNA` after chain material, tail is pure narration with **≥2** spoken turns).
2. **phrase** via a colon introducer «قال: …»; 3. **phrase** via colon-less «قال» (reverse scan,
   skip if a transmission verb follows — still inside the chain); 4. **phrase** via «أنّ النبيّ…»;
   5. **matn-only** when no transmission marker at all; 6. **none**.
   Finally `_trim_grade_tail` drops a trailing al-Ḥākim/Tirmidhī grade or takhrīj («هذا حديث صحيح…»,
   «على شرط…», «وفي الباب…»).
   > This is the **#102 "incomplete matn" fix**: previously the matn took only the first span and
   > stopped at a >40-char gap, dumping the story into the isnad. Verified: 2034 matns improved,
   > ~88 grade tails trimmed, 0 real matn lost.

**`hadith_extract.iter_hadith`** scans the page stream, detecting the marker style (`• [N]` vs
`N -`) over content pages, accumulating across page breaks, treating «باب/كتاب/فصل…» lines as
chapter headings (not phantom ḥadīth), and making reference entries («نحوه/مثله») inherit the
previous matn (`matn_confidence="ref"`) so parallel narrations are searchable.

**`rijal_extract.parse_rijal_file`** — terse رجال books (تقريب 8609 = the authority, الكاشف 2171).
Segments on `_BOUNDARY` (a numbered «N- » line), anchors the verdict on the طبقة (`_TABAQA`), reads
the operative grade word just before it (`_PRIMARY`, with al-Dhahabī fallbacks `_FALLBACK`), cuts
the name at the first bio cue/verdict (`_trim_name`), parses death-year (digits in الكاشف /
spelled-out in تقريب) — anchored on the «سنة» *followed* by a number so a narrator's **age** («مات
وهو ابن ٨٧ سنة») is never read as a death year (#118; a wrong year had caused false same-man merges).
**Four junk drops** (these would *contain-match* and mis-grade fuller
namesakes — a correctness concern, not just noise):
1. truncated «… بن» (nasab cut off); 2. generic «عبد الله»/«عبيد الله»; 3. **single identifying
token** («خالد»); 4. **bare ism+father with the gravest verdict** (كذاب/وضاع) lacking
nisba/kunya/death-year. Output: `{name, grade, source:"… (رقم N)", kunya?, aliases?, death_year?}`.
Grade robustness (verified on the real تقريب/الكاشف): **Companions are graded by DESCRIPTION** — `_COMPANION`
catches «ابن عم رسول الله»/«صحبة»/«خادم رسول الله»/«شهد بدرًا»… (gated on *no* طبقة), so ابن عباس/أبو سعيد
aren't «غير معروف»; a **كذب-accusation made out of enmity** («أعداؤه يرمونه بالكذب») is dropped, a critic's
own «رماه فلان بالكذب» kept; **`[إا]مام`** is hamza-tolerant for al-Kashif's «الامام» (مالك/الشافعي → ثقة);
and a <100 **death year is century-completed from the طبقة** («من العاشرة … ست وثلاثين» = 236). The
remaining long tail is the job of `build_rijal_llm` (see §5).

**`jarh_extract`** (الجرح والتعديل 2170) and **`tahdhib_extract`** (تهذيب الكمال 3722) extract a
who-from-whom **network** + multi-critic verdicts for the graph:
- jarh: footnotes stripped first (cut each page at the first `____`), name ends at `_NAME_END`,
  the **colon-less** network «روى عن…روى عنه…» split on the conjunction «و» (with a negative
  lookahead so «روى عنه» isn't read as شيوخ).
- tahdhib: every marker built diacritic-tolerant (`_alt`/`flexible_word`); minor narrators use the
  abbreviated **«عَن:» / «وعَنه:»** where **the colon is mandatory** — so the chain particle «عَنْ»
  (no colon) inside a sample isnad is never mistaken for a block opener. No `indexes.numbers` →
  the محقق's ~200-page intro is skipped by a **dense-rumūz window heuristic** (`_muqaddima_skip`:
  jump to the first window where ≥12/15 entries carry Six-Books symbols). Built coverage: ~6,870
  tarājim, books 92% / شيوخ 94% / تلاميذ 93% / verdicts 57%.

---

## 5. The رجال identification core (`app/rijal/`)

The heart of the system. Two layers meet at **build time** (`build_graph` + `build_rijal`) and at
**verdict time** (`qa/isnad.analyze_isnad`).

### `index.py` — the matching index
Match a chain name to a graded narrator entry by **ordered token containment**.
- `_clean_seq` strips honorifics, folds, drops `_STOP` tokens **including «بن»/«ابن»** (so
  «خالد بن عمر» and «عمر بن الخطاب» don't look alike through a shared «بن»), then de-dups
  preserving order.
- **Containment vs partial.** An entry whose tokens ⊆ the query is a containment match — accepted
  **only if it is the *leading run*** of the query (`query_seq[:len] == seq`): «… بن أنس بن مالك»
  is not أنس buried as an ancestor in the nasab; «عبد الله بن عمر بن الخطاب» is the son, not عمر.
  A query ⊆ a fuller entry is a *partial* (fragment) match. Containment always beats partial.
- **`_order_ok`:** shared tokens must appear in the same relative order in both → «يزيد بن جابر» ≠
  «جابر بن يزيد» (a different man).
- **Prefix preference:** when the query is the leading run of a form, that form wins; ties break to
  the shortest form.
- **Teknonym (أبو/أم) reverse-only:** a teknonym form (`_is_kunya_form`: 2 tokens starting with a
  kunya particle) matches **only** a query that itself starts with a kunya particle — a chain may
  cite a man *by* his kunya («أبو هريرة») but a bare ism «معمر» is **not** the man whose kunya is
  «أبو معمر».
- **Single-token guard:** a bare 1-token form can't identify a multi-token query.
- `lookup(name) → RijalMatch | None` (one best answer); `candidates(name)` returns the **full
  homonym set** (capped at 40 — a bare ism with dozens of bearers is too generic for the UI; pass
  `max_results=None` to lift the cap, which the mid-chain صحابي-demotion needs). The pivotal field
  **`grade_agreed = all tied candidates share one category`**.
- **Tie-breaking before context (both `lookup` and `candidates`):** `_prefer_non_coverage` drops a
  coverage-only namesake (الإصابة/الثقات) from a tied group when a real narrator is present; then
  `_prefer_prominent` (gated by `apply_prominence`) keeps only candidates ≥ ¼ as prolific as the most
  narrated (`set_prominence` ← `graph.frequencies()`). A bare-ism «ابن X» never lead-matches the
  *eponym* father (`nasab_ref`). Both `lookup` and `candidates` are **memoised** on the instance
  (cleared by `add`/`set_prominence`) — the joint resolver's pre-pass calls them per link over tens of
  thousands of chains.

### `grades.py` — verdict classification
`classify(text) → (category, rank)`. The **earliest-occurring** operative term wins; a `NEGATORS`
token in the 12-char window before a *positive* verdict cancels it («غير عدل» → «غير معروف»); a
صدوق with a weakening qualifier (يهم/اختلط/سيئ الحفظ…) becomes «صدوق له أوهام». Ranks:

```
صحابي 10 · ثقة 9 · صدوق 7 · صدوق له أوهام 6 · مقبول 5 · لين 4 · مجهول 3 · ضعيف 2 · متروك 1 · كذاب 0
```

### `canon.py` — chain-first disambiguation
`canonical(surface, context) → canonical name`. Two tiers:
1. **Context tier FIRST.** With a `context` (the other narrators' tokens) and >1 candidate, `_pick`
   chooses the homonym whose recorded **company** best overlaps the chain — *only* with a strict
   unique winner and real overlap, else keep the surface form. **"The chain before the name":**
   company decides *before* a bare namesake is trusted.
2. **Authority tier:** a confident context-free lookup (kunya→name, laqab→name, short→full nisba,
   nasab fragment). Anything weak/unknown/ambiguous-without-context is left as the surface form
   (never fuse two different men). `associations` come from a confident-only first pass.

### `resolve.py` — the joint resolver (تمييز المهمل بالشيخ والتلميذ)
The directional, anchored upgrade to `canon._pick` (which `analyze_isnad` calls as the last تمييز
lever, gated on the documented network being present). Why it beats `_pick`: `_pick` reads the *flat,
undirected* token company of a name's RAW (still-ambiguous) neighbours, so the disambiguation is
circular; this resolver uses the **documented direction** instead.
- `DocumentedNetwork` — one map `students[network_key(شيخ)] → {network_key(تلميذ)}`. The شيخ relation
  is its mirror («T شيخ of S» ⟺ «S تلميذ of T» ⟺ `S ∈ students[T]`), so a single dict serves both
  `is_student_of`/`is_teacher_of`. Built by `tahdhib.documented_students` (below), persisted to
  `data/documented_network.json` by `build_graph`, loaded by `audit_isnad` / `/verify-isnad`.
- `resolve_chain(candidates, anchors, network, route_starts) → resolved[]` — constraint propagation
  to a fixpoint. For an unfixed link, keep the homonyms documented as a تلميذ of its resolved شيخ
  (the link below, unless a ح route-seam) **or** a شيخ of its resolved تلميذ (the link above); if
  exactly **one** survives, fix it (and it anchors its neighbours next iteration), else hold.
  **POSITIVE-evidence only** — absence never rejects (the books' تلاميذ lists aren't exhaustive), a
  non-unique survivor is `None`. Anchors = the chain's confident unique-name matches; certainty
  spreads outward from them (typically from the terminal صحابي up). Bounded by network coverage;
  cascade-safe because the seeds are confident and it never overrides a specific match.

### `graph.py` — the company graph (شبكة الرواة)
SQLite `narrator(id, norm UNIQUE, name, freq)` + `link(teacher, student, weight)`. Node key =
**order-preserving folded tokens** (`node_key`, #111 — «أنس بن مالك» ≠ «مالك بن أنس», which are
anagrams in token space and are different men). Built by `add_chain` aggregating every adjacent
تلميذ→شيخ link. *(The separate `disambiguate` helper still uses sorted keys — latent, safe only while
its `_AMBIGUOUS` keys stay single-token.)*
- Every Prophet reference collapses to one node `PROPHET_NODE`.
- **The Prophet ﷺ is never a *student*** (#119): a pair whose التلميذ resolves to `PROPHET_NODE` (a
  mid-chain-parse «Prophet narrates from X») is dropped, keeping only the real «X → Prophet» edge — so
  an impossible edge can't pollute the company signal `canon._pick` consumes.
- **Kinship anchoring (the subtle part):** «حدثني أبي» / «أبيه» / «جده» name a real person *by
  relation* and must never become a hub. They resolve to the real ancestor pulled from the nasab,
  or to an **anchored placeholder** «جدّ X» / «والد X» (`is_unnamed_kin`) keyed to one narrator —
  so «جدّ X» ≠ «جدّ Y», the رجال layer never mis-grades it, and a later rebuild with richer data
  *promotes* it to the real person. (أُبَيّ بن كعب stays a real person.)
- `adjacency() → {name → sorted(شيوخ ∪ تلاميذ)}` is the function consumed to build the
  canonicalizer's company `profiles`.

### `muhmal.py` — تمييز المهمل from corpus redundancy *(the #110 lever)*
The same link «تلميذ ← X ← شيخ» is written bare in one chain, full in another; where a
`(تلميذ, شيخ)` context names X fully and uniquely, every bare X there *is* that man. Deterministic,
corpus-grounded, no grade, no external source — the classical method run over the whole corpus.
- `build_map(chains, min_count=2)`: for each **middle** node key by `(prev, next)` folded context;
  keep the **longest clean** form **only if it is unique at that maximal length** (rival full forms
  ⇒ genuine homonymy, left «مشترك») and occurs ≥ `min_count`. `_clean` rejects noise/verbs, a
  «وفلان» conjunction (a *second* narrator), stray digits, and >5 tokens.
- `resolve(name, prev, next, map)`: fires only for a **bare** name (1–2 tokens) and only when the
  bare is a **leading run** of the mapped full form («محمد» → «محمد بن جعفر» yes; «علي» no).
- Persisted to `data/muhmal.json`; applied in build_graph (before both passes) and at verdict time.

### `dedup.py` — same-man dedup *(the #109 lever)*
Collapses entries that are the *same man written two ways* across تقريب/الكاشف (which `merge_source`
couldn't unify), so a bare citation stops reading «مشترك» — **prudently, never fusing two
different men**.
- `ident_key(name)` = **ism + full father** (verified: `lin[0] + lin[1]`; compound father not
  truncated, so «عبد الله» ≠ «عبد الواحد») — the grouping key; only same-key entries are compared.
- `same_man(a, b)` cascade: require `lineage_compatible` (nasab chains agree on every shared
  ancestor) → no generation-marker conflict (الكبير/حفيد) → not disjoint nisba → **shared nisba ⇒
  same man unless `_strong_grade_conflict`** (one trusted, one weak — refuse) → else confirm by
  death-year (±20) or identical kunya, else **False**.
- **Prefix-extension «نقص قرينة» (built↔built, step 4):** the thin short form a chain cites carries
  none of the discriminators `same_man` needs (no nisba/death/kunya), so it stays split. `collapse`
  also folds such a short form into its **single** fuller man when lineage-compatible + same
  generation + no `_strong_grade_conflict`, **held** when it fits ≥2 distinct namesakes (`_all_nested`)
  or crosses the **طبقة boundary** (`_companion_split`: a صحابي and a definite non-صحابي of the same
  name are different men — صحابي vs ثقة is no grade conflict, so this is the lever that catches the era).
  This fold is name-conclusive, so under **mix** it is **not** subject to the company veto (the veto
  there only re-strands a coverage doubling the *stale* graph happens to split — the dedup-before-graph
  circularity); **strict** still requires `confirms`. The survivor keeps **both** critics' opinions, so
  a slight grade difference (صدوق↔مقبول) is preserved as the double-opinion, not flattened.
- **Corpus-company gate `CorpusCompany`** (reads the *previous* run's `narrators.db`): the name
  *proposes* a merge, the chain company can *veto* it. Policies: **mix** (default — merge unless the
  graph proves two distinct men with disjoint company; absent men trust the name), **strict**
  (`require_confirm` — absent men not merged), **name-only** (`company=None`).
- `collapse_duplicates(records, company)` groups by `ident_key`, unions pairs (union-find) gated by
  the policy, keeps the graded fullest-named primary, and preserves both critics' `opinions`.

### `tahdhib.py` — al-Mizzī's authoritative company (both flavours)
Turns each prose tarjama (تهذيب الكمال 3722, الجرح 2170, الثقات 96165 — `_NETWORK_SOURCES`) into
company, **only when the man resolves unambiguously**, two ways:
- `tahdhib_associations(records, rijal)` → `name → tokens of his شيوخ+تلاميذ` (UNDIRECTED, flattened).
  `build_graph` merges these into the pass-1 profiles, so `canon._pick` weighs the critics' company.
- `documented_students(records, rijal)` → `network_key(شيخ) → {network_key(تلميذ)}` (DIRECTIONAL,
  identity-level). It resolves each man **and** each quoted شيخ/تلميذ to a رجال canonical name and
  populates from both sides (a man's تلميذ; the man as a student of each of his شيوخ). This is the
  feed for `resolve.py` — the direction `tahdhib_associations` throws away. `build_graph` parses each
  book once for both, and writes the directional one to `data/documented_network.json`.

Gated: absent book ⇒ byte-identical behaviour, no extra pipeline step.

### `llm_source.py` — optional LLM-extracted رجال & chains *(the long-tail cure)*
Regex over terse Arabic prose is a long-tail bug factory (a single session needed ~9 hand-coded
fixes, and مالك بن أنس still came out of al-Kashif with a truncated kunya, the network in the grade
field, and no death year). The cure is **`scripts/build_rijal_llm.py`** — a build-time, cached pass
that uses the project's LLM (`config.py` engine) to **transcribe/segment, never author**:
- `--mode rijal` → `data/rijal_llm.jsonl`: `{name, kunya, grade_word, category, death_year, tabaqa,
  شيوخ[], تلاميذ[]}` — crucially the **network** the terse books drop.
- `--mode chains` → `data/chains_llm.jsonl`: a clean isnād/matn/narrators segmentation, **only** for
  chains the regex flags suspicious (`chain_is_suspicious`: 0 narrators, a verse ﴿…﴾ or matn word
  leaked into the terminal node) — the clean majority stays on the fast regex path.

**Faithfulness is enforced, not trusted** (it is نصّ الحديث + authoritative الجرح والتعديل): a grade
word absent from the tarjama, or an isnād+matn that doesn't reconstruct the source token-for-token,
is **rejected** (→ keep the regex). `app/rijal/llm_source.py` folds the output in, **all gated** —
no files ⇒ pure regex pipeline: `build_rijal` merges `rijal_llm.jsonl`; `build_graph` adds
`llm_associations` (network → `canon._pick` company, unambiguous men only); `parse_book_file(...,
llm_chains=)` overrides the flagged chains by a tashkeel-stable `text_key`.

---

## 6. Isnād verification & QA (`app/qa/`)

### `isnad.py` — the verdict-time consumer
`analyze_isnad(text, rijal=None, canon=None, muhmal=None, network=None)` first **splits the chain**
(transmission verbs incl. object-pronoun/قراءة forms; «ح» = a route seam; «أنّ» opens a report;
footnote digits stripped) — dropping what is never a narrator: a back-reference «بهذا الإسناد», a
hadith-number «م - ٢٣٤٥», a lone ramz letter, action verbs that open a matn («يخطب/يحدّث…», unless a
transmission verb follows) [#117], and — **only with `split_conarrators=True` (the graph-build path)** —
**splitting a waw-joined co-narrator** «الزهري وهشام بن عروة» into two nodes + a route-seam (guarded
against وكيع/أبو وائل/بن وهب/وسلم/وكان); the verdict path leaves it fused. A **تحويل (ح)** is a
*route seam*: the men either side are not a real link and not each other's company. When given the
rijal layer it grades each link via the **resolution ladder** (each rung only fires where the prior
left the name unchanged — none overrides a confident match):

0. **Joint-resolver pre-pass** (gated on `network`): build per-link candidates + anchors (unique-name
   matches) → `resolve.resolve_chain(..., route_starts)` → a resolved name per link, used at rung 4.
1. The Prophet ﷺ and a مبهم (unnamed) narrator are **never graded** (`match=None`).
2. **`muhmal.resolve`** — for a *middle* link, تمييز المهمل from the corpus map (records `resolved`).
3. **`canon.canonical(name, context)`** — if still مهمل, company disambiguation over the homonym
   set (`context` = the *immediate* neighbours' tokens, never across a ح seam).
4. **The joint resolver** — if STILL مهمل and the pre-pass resolved this link by the documented شيخ/
   تلميذ, take that identity (records `resolved`).
5. **`rijal.lookup(name)`** → `RijalMatch` (with the prominence prior + coverage drop applied inside).
6. **تمييز بالطبقة (position rule).** Only when the chain **reaches the Prophet ﷺ** is the terminal link
   a Companion → a صحابي homonym is preferred there; #117 gates this on `reaches_prophet`, so a تابعي in
   his own مقطوع (الأسود النخعي) is **not** force-promoted to الأسود بن سريع الصحابي. Symmetrically a
   صحابي match **deep** (≤ terminal−2) prefers a non-صحابي homonym (anachronism, reading the FULL homonym
   set via `candidates(apply_prominence=False, max_results=None)`), while the **penultimate** link keeps
   صحابي عن صحابي; an obscure-Companion-dictionary (الإصابة) man is dropped mid-chain (terminal-only).
6. **The grade-agreement gate:**
   ```python
   usable = match and (not match.ambiguous or match.grade_agreed
                       or (i == terminal_idx and match.entry.category == "صحابي"))
   ```
   An ambiguous match whose tied candidates **disagree** on the grade (عثمان بن أبي شيبة: ثقة vs a
   متروك namesake) is no confident identification → counted as **undetermined**, the chain is
   **held (يُتوقَّف), never graded weak**. When the tied candidates **agree** (عدي بن حاتم → both
   صحابي; الليث → both ثقة) — or a natural صحابي sits at the terminal — the grade is used. **The card
   still shows all candidates either way.**
   > The gate is a **safety net** — "don't get the verdict wrong" — **not** an identity resolver.
   > Identity is resolved by steps 2–3 (muhmal / company), not by the grade. See [§11](#11-identity-resolution-strategy--current-state).

`overall_ruling(analysis, continuity)` produces the single bottom line shown in «التدقيق» /
`/verify-isnad`:
- tone from the **weakest known link's rank** (`≤1`→ضعيف جدًا, `≤3`→ضعيف, `≤6`→حسن لغيره, `≤8`→حسن,
  else→صحيح);
- **any unknown narrator + positive tone → «يُتوقَّف فيه»** (the DB is limited — don't assert);
- a **مبهم** forces at least ضعيف (a real جهالة, independent of DB coverage);
- **continuity is a weak HINT only** — a broken link adds a caution but **never flips a sound chain
  to ضعيف** (the graph is built from the same corpus and keyed by canonical names, so a missing link
  is usually coverage/spelling, not real انقطاع);
- **عنعنة** → «صحيح إن ثبت السماع».

### `takhrij.py` — parallel-narration finder
`analyze_narrations(matn, …)`: gather candidates by lexical **OR-recall** (so paraphrases surface,
up to 3000) + semantic `vectors.search`; keep only same-*report* narrations (overlap-coefficient ≥
`_KEEP_OVERLAP=0.40` **or** cosine ≥ `_KEEP_SEM=0.78`); group **by Companion** then cluster into
صيغ (union-find on overlap ≥ 0.80 or cosine ≥ 0.92), label each بِلفظه/بنحوه/بمعناه, build the
«أخرجه …» line, and resolve «حسن صحيح» by the route count. Every narration carries `volume` for a
correct citation.

### `rulings.py` — ruling attribution & "double opinion"
`extract_rulings(text)` recognises attributed verdicts («صحّحه ابن حجر», «قال الترمذي: حسن صحيح»),
implicit ones («رواه البخاري» → that imam graded it صحيح, basis `تخريج`) and conditions («على شرط
الشيخين», basis `شرط`), each tied to a scholar + death-year and sorted by طبقة. **"Double opinion"**
has two realisations: text-level **divergence** (`collect_rulings` keeps conflicting verdicts;
`has_divergence` flags it) and narrator-level `RijalEntry.opinions` (`[{source, grade}]`, e.g. ابن
حجر vs الذهبي) — populated and displayed, not yet adjudicated (ROADMAP item 2). `extract_illal`
pulls stated defects (إرسال/وقف/تفرّد/شذوذ…).

### The rest
`answer.py` (cited extractive `/ask`, optionally LLM-synthesised, sources always returned),
`dossier.py` (composes hadith / narrator cards from all engines; never grades a synthetic
`is_unnamed_kin` node), `llm.py` (off by default; LiteLLM-routed local/remote, falls back to
extractive on any error), `intent.py` (routes a query to person vs text).

---

## 7. Search engine (`app/search/`)

- **`index.py` (FTS5).** Virtual table `hadith` with three indexed folded columns
  (`matn_norm, chapter_norm, isnad_norm`) + UNINDEXED payload incl. **`page` and `volume`**. bm25
  weights **`10.0, 4.0, 1.0`** (matn ≫ chapter ≫ isnad). Because FTS5's `snippet()` highlights only
  the *folded* column, the code **re-highlights the original** matn itself (`_excerpt`). `SharhIndex`
  splits passages into ~1400-char chunks and `full_passage()` re-joins them by `page_id`.
- **`vectors.py`.** `vec(id, v BLOB)` — float32 blobs; brute-force top-k cosine (numpy matmul or a
  pure-Python fallback). The whole set loads into RAM on first query (≈346 MB live). Ids shared with
  `index.db`.
- **`embeddings.py`.** `SentenceTransformerEmbedder` (Arabic model
  `…/Arabic-Triplet-Matryoshka-V2`, 768-dim) or, on any failure, a `HashingEmbedder` baseline that
  **substitutes silently** — "semantic" then degrades to a hashing approximation with no error.
- **`hybrid.py`.** `HybridSearcher` fuses lexical + semantic rankings with **Reciprocal Rank Fusion**
  (`rrf_fuse`, `k=60`); degrades to pure lexical when no vectors (`semantic_ready()` checks vector
  count). Lexical hits are SQL-filtered; semantic hits are filtered **post-fusion** — hence the
  deliberately deep candidate pool under filters. `_has_body` drops empty-matn rows (chapter markers).
- **`grouping.py`.** `cluster_reports` greedily groups same-report hits (overlap-coefficient ≥ 0.82,
  cap 500) so `/search` doesn't list one ḥadīth many times.

---

## 8. HTTP API & app skeleton

`app/main.py` mounts **10 routers**; **no startup DB connection** — each opens its sqlite singletons
lazily via `@lru_cache` on first request.

| Endpoint | Router | Notes |
|---|---|---|
| `GET /search` | search | `field`, `collection`, `grade`, `mode`(default **lexical**), `group`(default UI **report**); attaches `rulings` per hit |
| `GET /hadith/{id}` | search | one record |
| `GET /ask` | ask | RAG; `engine∈{auto,local,remote,off}`, `model`; falls back to extractive on error |
| `GET /takhrij` | takhrij | parallel narrations + flat `parallels` |
| `GET /verify-isnad` | verify_isnad | wires rijal + canon (from graph adjacency) + muhmal; returns `analysis`, `continuity`, `ruling` |
| `GET /audit` | verify_isnad | serves `data/audit.json` (`{available:false}` if absent) |
| `GET /narrator` | narrators | `narrator_dossier`; **503** no graph, **404** unknown |
| `GET /dossier` | dossier | unified front door; intent-routes person vs hadith |
| `GET/POST/PATCH/DELETE /notebook` | notebook | persists in `notebook.db` |
| `GET /sources` | sources | collections + commentaries + rijal editions |
| `GET /health`, `/health/ingestion` | health | status + crawl progress |
| `POST /admin/reload` | admin | `cache_clear()`s the on-disk providers → picks up rebuilt files **without restart** |

Skeleton: `config.py` (pydantic `Settings`/.env; LLM switch off|local|remote via LiteLLM),
`db.py` + `models/tables.py` (the **unwired** Postgres/pgvector path), `desktop.py` (pywebview window
over uvicorn on `127.0.0.1:8765`), `notebook.py` (sqlite, separate so it survives rebuilds).

---

## 9. The UI (`app/static/index.html`)

One RTL Arabic file (`<style>` + control bar + `#results` + one big `<script>`; **no external JS
libs** — CI runs `node --check` on the extracted script). **7 action tabs** (بحث / سؤال / تخريج /
راوٍ / الشبكة / الإسناد / دفتري) + **4 doc tabs** (التدقيق / المنهجية / البنية / التقنية). `run()`
dispatches on `mode`; all interactions use **event delegation on `#results`**.

- **`citeOf(x)`** renders «collection · رقم N · ج V · ص P», dropping missing parts. The **`ج V`
  (volume) is load-bearing** (per-volume page reset). Used on search cards, variant rows, copy-all,
  takhrij narrations, the isnad source card, and audit case detail.
- **Network tab** draws an **SVG graph by hand** (شيوخ above toward the Prophet, تلاميذ below; node
  colour = grade bucket, edge width ∝ log of count; click-to-recenter via `/narrator`).
- **Isnad tab** shows the «الحكم على الإسناد» verdict, chain features, each narrator graded with
  مشترك/مبهم badges, continuity links.
- The **المنهجية / البنية / التقنية** pages are hand-maintained reference arrays — **keep them in
  sync with behaviour changes** (an in-file maintenance contract).

---

## 10. The self-audit «التدقيق» (`scripts/audit_isnad.py`)

Rescans **every** chain in `index.db` through the same `analyze_isnad(rijal, canon, muhmal)` the live
verdict uses, and flags likely rijal-matching errors → `data/audit.json` (each a case for a human to
verify, not a verdict). Flags:

| Code | Meaning | Gate |
|---|---|---|
| **P** | the Prophet ﷺ graded as a narrator | any Prophet node carrying a grade |
| **S** | a صحابي graded mid-chain (Companions belong in the last 2 links) | **grade-agreement** (`certain`) |
| **W** | a fully-named narrator (≥3 tokens) graded متروك/متهم/كذاب/وضاع | **grade-agreement** (`certain`) |
| **A** | a مشترك (ambiguous match) | any ambiguous match |

**S and W fire only when `certain = not ambiguous or grade_agreed`** — an ambiguous match whose tied
candidates disagree on the grade is routed to **A** («مشترك»), never to a confident صحابي/متروك flag.
This is the audit-side expression of the same "hold, don't guess" rule. The audit consumes the
freshly-rebuilt `rijal.jsonl` + `muhmal.json` + `index.db` but the **previous** `narrators.db` (the
lag in [§2](#2-build-pipeline-the-8-steps)).

---

## 11. Identity-resolution strategy & current state

**The central problem.** The bulk of audit flags are **A («مشترك»)** — a name that matches more than
one man. A **grade is not an identity signal** (it says how good a man is, not which man he is), so
grade-agreement is only a *safety patch*; identity is fixed by **who sits around the man in the
chain**. The levers, in the order the verdict applies them (each only fires where the previous gave
up, and none overrides a confident specific match):

1. **Specificity — the name itself.** `index.lookup`/`candidates`: a uniquely-contained full name
   resolves outright; only genuine homonyms reach the context tiers. Coverage namesakes (الإصابة/
   الثقات — men outside the Six Books who barely narrate) are dropped from a tied group when a real
   narrator is present (`_prefer_non_coverage`), so an obscure namesake never makes a famous narrator
   «مشترك».

2. **Corpus redundancy — تمييز المهمل بالمسمّى.** `app/rijal/muhmal.py`: the same link is bare in one
   chain and full in another → the corpus names itself, deterministically. The شيخ-only relaxation
   keys on `(bare-ism, شيخ)` so a bare «يونس عن الزهري» resolves to الأيلي.

3. **Company — `canon._pick`.** The candidate whose recorded company (token overlap with the chain's
   neighbours, enriched by the prose sources' شيوخ/تلاميذ) best fits. **Its limit (the user's insight):
   the company is the *flat, undirected token bag* of a name's RAW neighbours — and those neighbours
   are themselves ambiguous, so a bare «عبد الله» beside the name carries no signal. The
   disambiguation is circular.**

4. **The joint resolver — تمييز المهمل بالشيخ والتلميذ.** `app/rijal/resolve.py` (wired into
   `analyze_isnad`, gated on `data/documented_network.json`). This breaks the circularity: it ANCHORS
   the links we are sure of (a unique-name match) and fixes each ambiguous link to the homonym
   **DOCUMENTED** (in تهذيب/الجرح/الثقات) as a تلميذ of its *resolved* شيخ (or شيخ of its resolved
   تلميذ) — a **directional, identity-level** constraint, not a token overlap — propagating to a
   fixpoint so certainty spreads up the isnād. POSITIVE-evidence only: a documented homonym is
   selected; absence never rejects, a non-unique survivor is held. It is the classical method the
   muḥaddithūn use, grounded in the curated books instead of the noisy corpus graph. Bounded by
   network coverage (تهذيب الكمال = the Six-Books men → good for the common case).

5. **Prominence — the frequency prior.** `index._prefer_prominent` (the `narrator.freq` column via
   `set_prominence`): a remaining tie breaks toward the much-narrated man (`ابن عمر` → عبد الله بن
   عمر), kept only when ≥ ¼ as prolific as the top — so two comparably-prolific men (سفيان عيينة/
   الثوري) stay a tie for the company to split. **Gated by `apply_prominence`**: the mid-chain
   صحابي-demotion calls `candidates(apply_prominence=False, max_results=None)` so it still sees the
   less-prolific تابعي homonym (else the commonest isms — عبد الله/محمد — collapse to the prolific
   *Companions* and regress to a false «صحابي mid-chain»).

6. **طبقة / position.** In `analyze_isnad`: the terminal link reaching the Prophet is a Companion
   (promote to the صحابي homonym); a صحابي DEEP in the chain is an anachronism (demote to a non-صحابي
   homonym); an obscure-Companion-dictionary (الإصابة) man is mid-chain-INERT (identified only at the
   chain's end). Grade-agreement is the final safety net (an ambiguous match whose candidates disagree
   on the grade is held يُتوقَّف).

**Node hygiene (a precondition for every lever).** The graph nodes and the documented network are only
as clean as the segmentation. Two-men-in-one-node corruption — a waw-joined dual «الزهري وهشام بن
عروة» (al-Zuhrī AND Hishām) — splits a real narrator's company off a fake node and pollutes the
documented network. `analyze_isnad(split_conarrators=True)` splits a co-narrator «وX» (guarded against وكيع/أبو
وائل/بن وهب/وسلم/وكان) into its own node + a route-seam — **gated to graph-build** (`build_graph` passes
it; the verdict path leaves the node fused, because in the audit the split surfaces the separated bare
ism as ambiguous (A↑) and trips the deep-صحابي flag on a Companion co-narrator (S↑), measured +4,320 A /
+97 S). So the graph/«راوٍ»/canon company get one man per node while the verdict keeps the old
segmentation. `scripts.audit_nodes` is the read-only detector that flags any node still carrying a
non-name fragment (verb/say/action/anna/backref/number) — it confirmed the split (1,868 → 21 corrupt nodes).

**Coverage sources.** الإصابة (صحابة, book 9767) and الثقات (book 96165) are merged ADD-ONLY
(`fill_gaps=False`) to pull men out of «مجهول»; their أقوال الأئمة (named-critic verdicts) attach via
`app/parsing/appraisals.py`. The risk they introduce (a common name/kunya shadowing a famous narrator
mid-chain) is contained by `_prefer_non_coverage` + the الإصابة mid-chain-inert guard.

**Measured arc (the user's real corpus, 84,783 chains · rijal 19,951).** The prominence prior + the
joint resolver took **A from 85,184 (pre-prominence) to 56,182 (−34 %, ≈29 k positions resolved)**
with **S 487 → 479 and W 659 → 631 — both flat-to-better** (no new wrong verdicts: the طبقة guards +
positive-evidence-only held). The joint resolver alone (network off→on) was **A −15 %** at a documented
network of **7,824 شيوخ** (تهذيب 2013 + الجرح 4313 + الثقات 4968). The متن audit (`audit_matn`) is
settled: **V 475 · empty 295 · I 372 · G 269 · Q 138**, the residual being short answers, isnad-in-matn
(LLM `--mode chains` territory), takhrīj tails and verses.

**The residual A, decomposed (what's left and why).**
- **②a/②b floor (سفيان 4097 = الثوري/عيينة).** Resolved where a *distinctive* شيخ/تلميذ anchors the
  chain; held where the man sits among the genuinely-shared ~15 % company or bare neighbours. The
  honest floor — only more company (network coverage) or the text itself can move it.
- **Name-granularity shadows (محمد بن جعفر 2161).** غندر is a candidate, but the documented network
  stored شعبة's student as the BARE «محمد بن جعفر» (+ a البزاز), so the resolver can't uniquely match
  غندر's full key → held (correct given the dirty data). Cure: upstream name consistency / dropping
  the bare shadow entry. *Open.*
- **Shuhra-by-ancestor (ابن جريج 1574).** The famous man is known by a *distant ancestor's* name
  (عبد الملك بن عبد العزيز بن جريج), so «ابن جريج» finds literal «X بن جريج» sons, not him. A distinct
  matching enhancement. *Open.*

**The principle.** The goal is **not A = 0** — it is «resolve what the text determines, hold the rest»
(لا نختلق). A genuine homonym with no distinguishing company is *correctly* held يُتوقَّف. The wins are
W/S (wrong verdicts) and the share of A that is truly recoverable; the irreducible floor is not chased.

---

## 12. Conventions & how to run

- **Run everything via `update.bat`** on the user's machine (`.venv\Scripts\python.exe`). The
  standalone launchers each do one step `update.bat` already chains; keep one app-launcher
  (`AVVIA_APP`/`AVVIA_FINESTRA`) since `update.bat` does not start the app.
- **Tests:** `PYTHONPATH=. python3 -m pytest -q`. CI also runs `node --check` on the `<script>`
  extracted from `index.html` — keep it valid JS. Update the in-app «المنهجية»/«البنية» pages when
  behaviour changes.
- **Workflow:** develop on the feature branch, then **merge to main via squash-PR** (because
  `update.bat` pulls `main`); after each squash-merge **realign the branch**
  (`git fetch origin main && git reset --hard origin/main && git push --force-with-lease`).
- **No model id / assistant identity** in any committed artifact.
- **Standalone build tools:** `python -m scripts.build_rijal [--no-download]` (rebuild
  `rijal.jsonl`), `python -m scripts.audit_isnad` (rebuild `audit.json`), `python -m
  scripts.measure_dedup` (read-only dedup vs homonymy), `python -m scripts.sample_source <id>`
  (read-only prose-rijal sampler).
