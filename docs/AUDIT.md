# Hadith Research Backend — Code Audit & Remediation Plan

**Date:** 2026-06-06 · **Baseline:** `154 passed, 1 skipped`. Findings are real and, where noted,
reproduced (several on live turath data: البخاري 1284, مسلم 1727, تقريب 8609, الكاشف 2171).
None are caught by the current test suite — they are uncovered gaps, not regressions.

## How the audit was done (methodology)
Five parallel reviewers, one per subsystem, each with a subsystem-specific checklist, required to
prove every defect with a `file:line` and (where feasible) a reproduction on real data. Every defect
is rated **Critical / High / Medium / Low** by its effect on *the trustworthiness of the result a
student relies on* (a wrong صحيح/ضعيف verdict is worse than a crash). Domains audited: parsing &
extraction; narrator network & isnad; search/تخريج/أحكام; API/config/LLM/persistence;
frontend & build pipeline.

## Executive summary
- **6 Critical**, **16 High**, **~16 Medium**, **~10 Low**.
- The dominant risk is **wrong authenticity output**: a chain can be graded «رجاله كلّهم ثقات / صحيح»
  when it is not, and a scholar's «ضعيف» can be recorded as «صحيح». These are not crashes — they
  silently mislead.
- Cross-cutting themes (fix once, fix many):
  - **A — Negation is ignored everywhere** a verdict/grade is read (hadith grade, rijal verdict,
    scholars' rulings) → «لم يصحّح»/«غير عدل»/«ليس بصحيح» flip to positive.
  - **B — The isnad↔matn boundary is fragile** → matn leaks into the last narrator's name (the
    reported شيوخ pollution), the Prophet isn't unified, relatives become a fake hub.
  - **C — Narrator matching over-trusts single-token names** → weak/unknown narrators resolve to
    Companions (rank 10).
  - **D — الكاشف extraction is broken** (50% polluted names, 30% missing grades).
  - **E — Ruling attribution crosses clause boundaries** → verdict credited to the wrong scholar.
  - **F — API robustness/safety** (LLM crash hidden as "engine down", no timeout, weak validation,
    stale caches, attribute-XSS in the notebook note).

---

## Findings catalogue

Severity key: **[C]** Critical · **[H]** High · **[M]** Medium · **[L]** Low.

### Theme A — Negation & verdict reading (authenticity integrity)
- **GRD-1 [H]** `app/parsing/grading.py:18-46` — hadith grade extracted with **no negation guard**:
  `إسناده غير صحيح` / `لا يصح` can return the *positive* grade. Worst possible direction.
- **GRD-2 [H]** `app/qa/rulings.py:168-187` — scholar-ruling extraction ignores negation:
  `لم يصحّح الألباني` → `(الألباني, صحيح)` (reproduced).
- **GRD-3 [M]** `app/rijal/grades.py:54-67` — `classify` ignores negation: `غير عدل` → `ثقة` (rank 9);
  `ليس بحجة` and `وثقه ابن معين` are dropped to «غير معروف» (clitic `ب`/`و` defeats the word match).

### Theme B — Isnad↔matn boundary & narrator identity
- **ISN-1 [C]** `app/qa/isnad.py:88-109` (with `_SKIP` at `:32`) — **matn leak**: `قال` is `continue`d
  without `flush()`, so `… عن النبي ﷺ قال <matn>` fuses the whole matn onto the last narrator's name.
  Reproduced: `عن أبي هريرة قال إنما الأعمال` → narrator `"أبي هريرة إنما الأعمال"`. **Root of the
  reported شيوخ pollution.**
- **ISN-2 [C]** `app/rijal/graph.py:118-135` — **Prophet never consolidated**: `is_prophet()`/`_PROPHET`
  exist (`:37,48`) but `add_chain` doesn't use them; node identity is the folded token set, so
  «النبي يقول», «رسول الله», «النبي مثله» become different teacher nodes. `is_prophet` is also too
  strict (requires the *whole* token set ⊆ Prophet terms, so «النبي مثله» is missed).
- **ISN-3 [H]** `app/qa/isnad.py:160-175` + `:191-223` — the matn leak makes the last link unknown →
  `continuity` reports a false **انقطاع** → `overall_ruling` overrides an otherwise-ṣaḥīḥ chain to
  ضعيف «انقطاعٌ ظاهر» (reproduced). A real, wrong verdict.
- **ISN-4 [H]** `app/qa/isnad.py:93-109` → `app/rijal/graph.py` — **relatives become nodes**:
  `عن أبيه عن جده` emits literal `أبيه`/`جده`; across the corpus all `أبيه` merge into one bogus hub
  that is everyone's teacher/student.
- **ISN-5 [M]** `app/qa/isnad.py:98-108` — the **«و» co-narrator** pattern fuses two men:
  `أبو بكر وعمر قالا` → one narrator `"أبو بكر وعمر"`.
- **ISN-6 [L]** `app/qa/isnad.py:116` — `reaches_prophet` is a substring test over the *whole* text
  (matn included) → a mawqūf report whose matn mentions النبي is mislabelled marfūʿ; the
  `رسول اللـه` (tatweel) alternative is dead code.
- **ISN-7 [L]** `app/parsing/normalize.py` vs `app/rijal/index.py:26` — `strip_diacritics` doesn't
  strip the ﷺ ligature (U+FDFA), so the stored/displayed name keeps it (display noise only).

### Theme C — Narrator matching over-grades
- **RIJ-1 [C]** `app/rijal/index.py:120-140` (containment rule `:127`) — a name **form that is a
  subset of the query scores 1.0**. Single-token seed aliases («عمر», «أنس», «جابر») then match any
  query containing that token: `lookup("خالد بن عمر")` → **عمر بن الخطاب (صحابي, rank 10)**;
  `lookup("عمر بن علي المقدمي")` → عمر بن الخطاب (reproduced). Weak/unknown narrators are silently
  promoted to Companions → «رجاله كلّهم ثقات»; the `ambiguous` flag isn't even raised.
- **RIJ-2 [H]** `app/rijal/graph.py:71-85` — disambiguation uses only the **two immediate** neighbours
  and only knows سفيان/حماد; other shared names (محمد …) and far-placed markers are missed, so
  distinct men merge into one node (reproduced: two different «سفيان» merged).

### Theme D — rijal extraction (data quality)
- **RIJ-3 [C]** `app/parsing/rijal_extract.py:60-63` (`_NAME_CUT`) + `:144-160` — **الكاشف fails**:
  `سمع` (al-Dhahabī's teachers cue) isn't a name-cut token and there's no طبقة, so the name swallows
  teachers+verdict+bio. Measured on real الكاشف pp.182-183: **50% polluted names, 30% «غير محدد»**
  (vs 0%/7% for تقريب).
- **RIJ-4 [H]** `app/parsing/rijal_extract.py:40-57` — verdict vocabulary gaps: `الحافظ`/`الإمام`
  (definite article blocks `_PRIMARY` word-boundary), `نسبه … إلى الكذب`, OCR-glue `صدوقتوفي` → a
  liar or a top ḥāfiẓ is graded «غير محدد».

### Theme E — scholars' ruling attribution (أحكام)
- **RUL-1 [H]** `app/qa/rulings.py:177-182` — after «قال X», the verdict window (`i+1:i+12`) **crosses
  the next clause/scholar**: `قال أحمد … رجاله ثقات وقال الدارقطني هو ضعيف` → `(أحمد, ضعيف)`
  (reproduced). The verdict is credited to the wrong critic.
- **RUL-2 [M]** `app/qa/rulings.py:170,179` — the scholar window is **forward-only**, so the very
  common `ابن حجر صححه` / `الألباني ضعفه` (scholar *before* the verb) is missed entirely.
- **RUL-3 [M]** `app/qa/rulings.py:184-187` — implicit takhrij picks only the *nearest* scholar, so
  `رواه النسائي والبخاري ومسلم` emits **no** implicit صحيح (البخاري/مسلم not nearest).
- **RUL-4 [M]** `app/qa/rulings.py:24` — bare «مسلم» is a scholar form → `قال رجل مسلم هذا صحيح` →
  `(مسلم, صحيح)`. False ruling attributed to Imam Muslim.

### Theme F — search & retrieval
- **SRCH-1 [H]** `app/search/hybrid.py:81-98` — in `hybrid`/`semantic`, the `collection_id`/`grade`
  filter is applied **after** RRF on a bounded pool, so deep matches are discarded:
  `search(..., collection_id=2, mode="hybrid")` can return **0** though matches exist (reproduced).
- **SRCH-2 [M]** `app/search/index.py:213,360` — `snippet()` highlights the **folded** (`*_norm`)
  column, so the preview shown to the user is diacritic-stripped, mangled Arabic.
- **SRCH-3 [M]** `app/search/embeddings.py:63` — `cosine` uses `zip` → **silently truncates** on a
  dimension mismatch (wrong score, no error) on the pure-Python path; numpy would raise. Diverging
  failure modes.
- **SRCH-4 [M]** `app/qa/takhrij.py:80-88` — `_companion_of` matn fallback mis-attributes when a
  Companion is merely *mentioned* in the matn (reproduced: chain with no Companion + «أبا هريرة» in
  the body → attributed to Abū Hurayra).
- **SRCH-5 [M]** `app/qa/takhrij.py:137-166` — single-linkage union-find chains distinct wordings
  (A~B, B~C ⇒ A,C merged) → distinct صيغ collapse; under-counts variants.
- **SRCH-6 [L/M]** `app/search/vectors.py:79-84` — numpy vs pure-Python **tie-break order differs**
  for equal cosines → backend-dependent ranking.
- **SRCH-7 [L]** `app/search/index.py:199` — unknown `field` value silently searches all columns.
- **SRCH-8 [L]** `app/qa/takhrij.py:91-99` — `_takhrij_line` drops collections whose narrations are
  all `number=None` (by-chapter editions).

### Theme G — parsing structure (hadith/sharh)
- **PARSE-1 [C]** `app/parsing/isnad_matn.py:38-41` — matn spans first-open → **last**-close quote, so
  any text between two quoted spans (a `قال أبو عبد الله …` tail comment, a «…» takhrij note) leaks
  into the matn (reproduced; also caused real content loss on Bukhari pg.153-154).
- **PARSE-2 [H]** `app/parsing/hadith_extract.py:64` + `grading.py:23` — grade is read from the
  **whole** text, so `حديث حسن` / `باب … حديث صحيح` *inside the matn* yields a false editorial grade.
- **PARSE-3 [H]** `app/parsing/hadith_extract.py:37,127` — bare `N -` **bab headings** (not in a
  title span) are matched as phantom hadiths with empty matn, corrupting dash-style numbering.
- **PARSE-4 [M]** `app/parsing/sharh_extract.py:101-130` — by-chapter sharh attributes a whole page
  to the **last** title on it, so page-straddling commentary lands under the wrong باب.
- **PARSE-5 [M]** `app/parsing/sharh_extract.py:83-98` — by-number sharh duplicates the **full page**
  to every hadith number sharing that page.
- **PARSE-6 [M]** `hadith_extract.py:157` / `rijal_extract.py:212` / `sharh_extract.py:73` —
  front-matter skip uses `min(page)` of the numbers index; one outlier (a muqaddima cross-ref, a `0`)
  drags the start back into the muqaddima.
- **PARSE-7 [L]** `hadith_extract.py:37` — dash marker misses glued sub-numbers `١ -(١)` and tatweel
  dashes `١ـ`.
- **PARSE-8 [L]** `hadith_extract.py:124,141` — `<s0>` grade↔hadith positional pairing desyncs across
  page breaks. **PARSE-9 [L]** `sharh_extract.py:52` — chapter headings keep `(^N)` footnote refs.

### Theme H — normalization
- **NORM-1 [M]** `app/parsing/normalize.py:21` — `normalize_for_search` strips **Latin** digits `0-9`
  but keeps **Arabic-Indic** `٠-٩` → a query in Latin digits never matches text in Arabic-Indic.
- **NORM-2 [M]** `app/parsing/normalize.py:21` — non-core letters are **deleted**, not mapped:
  Persian kāf `ک`, yā `ی`, `ھ`, and presentation ligatures (`ﻻ`) → `کتاب علی` → `تاب عل`. Corrupts
  search & rijal matching for OCR text using these glyphs.

### Theme I — API / config / LLM / persistence
- **API-1 [C]** `app/qa/llm.py:31-33` — `_sources_block` does `ref += …` where `ref = s.get("sharh")`
  can be `None` → `TypeError` whenever a retrieved شرح has a null title. The whole LLM answer path
  fails (and is then hidden by API-2).
- **API-2 [H]** `app/routers/ask.py:80-89` — `/ask` wraps the synthesizer in a blanket
  `except Exception` that reports *every* error (incl. API-1, KeyErrors) as "engine unreachable /
  check your API key". Real bugs are invisible and untestable; no logging.
- **API-3 [H]** `app/routers/notebook.py:36-58` + `app/notebook.py` — untyped `dict` bodies; a
  `list`/`dict` for `tags`/`note`/`body` → `sqlite3.ProgrammingError` → **500** (should be 422).
- **API-4 [H]** `app/routers/notebook.py:45` — `meta` accepted as a scalar/list, round-trips as a
  non-object → silent data-shape corruption for consumers doing `meta["grade"]`.
- **API-5 [H]** routers `search`/`ask`/`verify_isnad`/`notebook` — `@lru_cache` provider singletons
  open the sqlite/index once and are **never invalidated**; after a re-index the server serves stale
  data (or errors on a replaced file) until restart. No `cache_clear`/reload path exists.
- **API-6 [H]** `app/qa/llm.py:55-63` — `litellm.completion` is called with **no timeout** → a wedged
  Ollama/cloud provider blocks the worker thread indefinitely; the "graceful fallback" never fires.
- **API-7 [M]** `app/routers/health.py:26-31` — `/health/ingestion` 500s on a half-written manifest
  (`JSONDecodeError`) or a missing `status` key — exactly during a live crawl.
- **API-8 [M]** `app/qa/llm.py:69-102` — provider keys other than the two typed settings are read
  from a **CWD-relative `./.env`**, so `GEMINI_API_KEY`/`GROQ_API_KEY` set in `.env` fail when the
  process runs from another directory (systemd, container, the desktop launcher).
- **API-9 [M]** `app/routers/search.py:59` — `limit` has `ge=1` but no `le=` → `limit=10_000_000` is
  a resource-exhaustion vector (also large `k` in `/ask`,`/takhrij`).
- **API-10 [M]** `app/qa/llm.py:22-40` — retrieved corpus text is concatenated raw into the prompt
  with no delimiting → prompt-injection can override "answer only from sources / cite / never invent".
- **API-11 [L]** `app/qa/llm.py:64` — `response["choices"][0]…` dict-subscripts an SDK object and
  doesn't coalesce `None` content. **API-12 [L/M]** `app/notebook.py:33-85` — request-time writes on
  one shared `check_same_thread=False` connection without a lock (concurrent POST/PATCH/DELETE).

### Theme J — frontend
- **FE-1 [H]** `app/static/index.html:239` — `esc()` escapes `< > &` but **not `"`/`'`**, and its
  output is interpolated into double-quoted attributes (the notebook **note**, `:531`, is
  user-authored & persisted) → attribute-injection / stored XSS.
- **FE-2 [M]** `app/static/index.html:347` — the `/^\d+$/` hadith-id test fails on **Arabic-Indic
  digits** (`١٢٣٤`), so a number typed in native digits is sent as an isnad → 422 / nonsense.
- **FE-3 [L/M]** `app/static/index.html:311-358` — `search`/`ask`/`takhrij`/`notebook` branches don't
  check `r.ok`, so non-OK JSON responses are shown as "no results" and 5xx as "server is down".
- **FE-4 [L]** `:616` toggle handler assumes `nextElementSibling` is the isnad div (no null guard).
- **FE-5 [L]** `:8` Google-Fonts `@import` is a network dependency (graceful serif fallback exists).

### Theme K — build pipeline & ingestion
- **PIPE-1 [M]** `app/ingestion/downloader.py:108-176` — on resume after a transient `/book` info
  failure, `_write_pages` rewrites the file with `meta=None`/`indexes=None`, **destroying** the
  previously-saved headings & number→page map that parsing depends on.
- **PIPE-2 [L/M]** `scripts/_atomic.py:29-43` — if `build()` raises, the `*.tmp` file and the open DB
  handle leak (no `try/finally`); on Windows the orphaned handle breaks the next rebuild's
  `tmp.unlink()` — contradicting the module's stated Windows-lock safety.
- **PIPE-3 [L]** `scripts/parse.py:26-34` — `_is_sharh` reads & JSON-parses the **whole** book file
  just to read `cat_id`, then parses it again (doubled I/O across the corpus).
- **PIPE-4 [L]** `app/ingestion/downloader.py:142` — `--limit-pages` smoke runs mark a book
  `"complete"` from the capped count. **PIPE-5 [L]** `:130` — a genuinely empty page-1 book stays
  `"partial"` forever. **PIPE-6 [L]** `scripts/update.py:43` — step numbering is inconsistent
  («2/5» then «3/7»; `--semantic` never updates the denominator).

### Cross-cutting opportunity
- **PERF-1** `scripts/embed.py` re-embeds the **entire** corpus on every `update --semantic`
  (~86k hadith) even when nothing changed → make embedding **incremental** (only new/changed matns).

---

## Remediation plan (professional, staged)

Principle: **prove, then fix.** Each wave starts by adding regression tests that *reproduce* the
bugs (red), then makes them green, then merges behind a green suite. Waves are ordered by harm to
the trustworthiness of the output. One focused PR per wave (or per theme within a wave).

### Wave 0 — Safety net (do first)
- Add a **CI workflow** (GitHub Actions): `pip install -e .[dev]`, `pytest -q`, and `node --check`
  on the extracted UI script, on every PR.
- Add **reproduction tests (red)** for every Critical & High below, so the fixes are verifiable and
  locked against regression.

### Wave 1 — Authenticity integrity (Critical correctness)
Fix the bugs that produce *wrong verdicts*:
1. **RIJ-1** — require a minimum specificity for a containment match (ignore <2-token forms as
   standalone confident hits; demote to ambiguous when the query carries discriminating tokens the
   form lacks). Stop indexing bare single-token aliases as authoritative forms.
2. **Theme A (GRD-1/2/3)** — one shared **negation guard**: if a negator (`غير`,`ليس`,`لا يصح`,
   `لم يثبت`,`لم يصحّ`…) precedes a grade/verdict token within a small window, reject/invert. Apply in
   `grading.py`, `rulings.py`, `grades.py`.
3. **ISN-1/2 + ISN-3** — make the chain parser **stop at the matn**: flush + terminate on
   `قال/قالت/قالوا` that begins matn, and treat `is_prophet()` as the terminal node; canonicalise any
   Prophet reference to a single «النبي ﷺ» node in `add_chain`; relax `is_prophet` to "core tokens
   are a Prophet term". This fixes the شيوخ pollution and the false انقطاع.
4. **ISN-4** — exclude/resolve relatives (`أبيه/جده/ابنه/عمه/أخيه…`): don't create shared nodes.
5. **RUL-1/2** — truncate the verdict window at the next scholar/verb/`قال`; add a small **backward**
   window for the `scholar صححه` order; **RUL-4** drop bare «مسلم».
6. **API-1** — null-coalesce the شرح title (`ref = s.get("sharh") or "شرح"`) and guard matn/excerpt.

### Wave 2 — Data quality (extraction)
7. **RIJ-3/4** — add `سمع`,`وعنه`,`روى عنه` to `_NAME_CUT`; when there's no طبقة, set `name_end` to
   the earliest verdict/teacher cue; allow an optional `ال` before `_PRIMARY` terms; add
   `الكذب/نسبه…الكذب/خلط` and tolerate the `صدوقتوفي` glue. Re-measure الكاشف pollution → target <5%.
8. **PARSE-1** — match the **first balanced** quoted span (pair the opener with its closer), keeping
   adjacent dialogue; stop swallowing inter-quote prose. Re-verify on Bukhari 153-154.
9. **PARSE-2** — read the grade only from ruling-bearing regions (footnotes/`<s0>`/post-matn), not
   the matn body; require the `حديث`-cue near a ruling marker.
10. **PARSE-3** — reject a dash segment whose head is `باب/كتاب/فصل/جماع` or matches `meta.headings`.
11. **SRCH-1** — push `collection_id`/`grade` into vector retrieval (or grow the pool until `limit`
    survivors), so filtered hybrid/semantic search doesn't under-return. **SRCH-2** — build the
    snippet from the original (un-folded) text.

### Wave 3 — Robustness & safety
12. **API-2** — narrow `/ask`'s except to provider/IO/ImportError, **log** unexpected errors, let
    them surface. **API-6** — pass `settings.llm_timeout` to `litellm.completion`. **API-10** —
    fence sources in `<sources>` and instruct the model to treat them as data.
13. **API-3/4** — replace untyped notebook bodies with Pydantic `NoteCreate`/`NoteUpdate` (str
    fields, `dict` meta → 422 on mismatch). **API-12** — guard notebook writes with a `threading.Lock`.
14. **API-5** — add a small **admin reload** endpoint (or mtime-keyed cache) that `cache_clear()`s
    the providers and closes stale connections; document "restart after re-index" meanwhile.
15. **API-9** — add `le=` caps to `limit`/`k`. **API-7** — guard the manifest read. **API-8** —
    resolve the env-file path from `Settings.model_config` (single source of truth).
16. **FE-1** — make `esc()` also escape `"`/`'` (or use DOM APIs for attributes). **FE-2** —
    normalise Arabic-Indic/Eastern digits before the id test. **FE-3** — check `r.ok` in every branch.
17. **PIPE-1** — preserve existing `meta`/`indexes` when the info fetch fails. **PIPE-2** — wrap
    `build()` in `try/finally` that closes the handle and unlinks the `*.tmp`.

### Wave 4 — Consistency, polish, performance
18. **NORM-1/2** — fold Arabic-Indic+Persian digits to Latin and keep `0-9`; pre-map `ک/ی/ھ` and
    presentation ligatures (NFKC) before the strip.
19. **RIJ-2 / SRCH-5 / SRCH-3 / SRCH-6** — widen disambiguation window & don't merge un-resolved
    shared names; complete/average linkage for صيغ; length-check `cosine`; unify tie-break order.
20. Remaining Mediums/Lows: SRCH-4/7/8, RUL-3, PARSE-4..9, ISN-5/6/7, intent `عرّف بـ`, PIPE-3..6,
    API-11. **PERF-1** — incremental embedding (only changed matns) so `update --semantic` doesn't
    re-embed ~86k hadith each time.

### Verification per wave
`pytest -q` green + the new reproduction tests + a real-data spot check on the affected path
(e.g. عمر's شيوخ = a single «النبي ﷺ»; الكاشف pollution <5%; a known weak chain reads ضعيف, a known
ṣaḥīḥ chain reads صحيح). Merge each wave to `main` via its own PR.

---

## Test-coverage gaps to close (folded into the waves)
- No test feeds a full `… عن النبي ﷺ قال <matn>` chain (would catch ISN-1/2/3).
- No `RijalIndex` test asserts an **absent** narrator does *not* match a Companion (RIJ-1).
- No الكاشف-format rijal fixture (RIJ-3/4); no negation tests anywhere (Theme A).
- No multi-clause / scholar-before-verb / negation ruling tests (RUL-1/2, GRD-2).
- No hybrid+filter, snippet-orthography, numpy-path, or takhrij mis-attribution tests.
- No frontend harness (esc/quotes, Arabic digits); no `_atomic` failure-cleanup or downloader
  resume-meta tests.

## Verified non-issues (ruled out — do not "fix")
- FTS5 MATCH is safely escaped/quoted (no injection). Arabic normalization is **consistent** between
  index and query. `grade="صحيح"` correctly excludes «حسن صحيح». Remote `api_base` is correctly
  `None` (no localhost-for-cloud regression); `anthropic/claude-sonnet-4-6` is valid. RRF formula,
  composite-verdict ordering, era sorting, retry/backoff + zstd + manifest atomic-save are correct.
  Regexes are bounded (no catastrophic backtracking).
