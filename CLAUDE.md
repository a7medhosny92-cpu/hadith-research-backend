# CLAUDE.md — operating memory for this project

Read at the start of every session. This is the project's **durable memory** — trust it over
recollection, and **keep the "Current work" section updated as we go**. (The user explicitly asked
to track the work: long conversations get summarised and detail fades, so the reliable memory is
the file, not my recall. When asked how something we built works, **re-read the file, don't guess.**)

## What this is
Hadith research RAG backend in classical Arabic: search, Q&A, takhrīj, and **isnad verification**
over the great collections, with citations and narrator (رجال) gradings. Local-first, CPU-only,
single user. Stack: FastAPI + SQLite + sentence-transformers; desktop app via pywebview; single-file
vanilla-JS/SVG UI at `app/static/index.html`.

Depth docs (NOT auto-loaded — open when relevant):
- `docs/ARCHITECTURE.md` — **start here**: consolidated, code-accurate map of the whole system
  (pipeline, parsing, رجال core, QA, search, API/UI, audit) + the identity-resolution strategy.
- `docs/DISAMBIGUATION_FINDINGS.md` — remote Ṣaḥīḥayn-subset measurement session: the certainty
  analysis + **the `canon._pick` silent-mis-identification bug** (يونس عن الزهري → wrongly يونس بن عبيد)
  and the neighbour-roster fix. **Read before touching narrator disambiguation.**
- `docs/ROADMAP.md` — forward plan. **Item 8 = rich rijal from تهذيب الكمال; item 2 = double-opinion.**
- `docs/AUDIT.md` — the big code audit (findings GRD-/ISN-/RIJ-…, mostly since fixed).
- `README.md` — overview & how to run.

## How it runs (operational — I got this wrong once; get it right from the file)
- **`update.bat`** (double-click) → `python -m scripts.update`: an **8-step pipeline, not just git
  pull** — checkout main → `git pull --ff-only` → deps → **download books** → parse → index → build
  narrator graph → **build_rijal** → **audit** (regenerates `data/audit.json`, the «التدقيق» tab).
  - Downloads are **incremental & resumable** (`data/raw/turath/manifest.json`; already-complete
    books are skipped). It does **not** re-download what's cached.
  - Parse / index / build_rijal **re-run every time** (idempotent) on the cached books — so a code
    fix to extraction/matching takes effect here **even with no new download** (step 8 rebuilds
    `rijal.jsonl`).
  - `update.bat --code-only` = pull + deps only → does NOT rebuild rijal.jsonl.
- **`python -m scripts.build_rijal [--no-download]`** → rebuilds `data/rijal.jsonl` from
  تقريب(8609)+الكاشف(2171). `--no-download` re-parses cached books only (fast — applies an
  extraction fix in seconds without the full update).
- **`python -m scripts.build_rijal_llm --mode rijal|chains [--engine local|remote] [--sample N] [--dry-run]`**
  → **LLM-assisted, FAITHFUL** build-time extraction (the regex's long-tail cure). `--mode rijal` →
  `data/rijal_llm.jsonl` (grade + **شيوخ/تلاميذ network** + death/kunya the terse regex drops);
  `--mode chains` → `data/chains_llm.jsonl` (re-segment isnād/matn only for chains the regex flags
  suspicious). The LLM only **transcribes/segments verbatim**; every record is **validated against
  the source and rejected** (→ regex fallback) otherwise. Cache by hash; `--dry-run`/`--sample` to
  preview. **Auto-used by the pipeline when the files exist** (GATED → absent = pure regex pipeline):
  `build_rijal` merges the rijal, `build_graph` adds the network to `canon._pick`'s company,
  `parse` overrides the flagged chains. See `app/rijal/llm_source.py`.
- **`python -m scripts.audit_isnad`** → rescans all chains → `data/audit.json` (the «التدقيق» tab).
  **Run by update.bat as its final step** (so a plain update refreshes W/S/A); also runnable standalone.
- **`python -m scripts.measure_dedup [--input f.jsonl]`** → read-only: how much of «مشترك» is the
  same man twice vs genuine homonymy.
- **`python -m scripts.sample_source <id> [--entries N|--find "name"|--pages A-B] --out f.txt`** →
  read-only sampler to study a *prose* rijal source before writing its extractor; downloads the book
  if absent; never touches rijal.jsonl. Ids: تهذيب الكمال 3722, تهذيب التهذيب 1278(دبي)/1293(الرسالة).
- The user runs everything on their PC with `.venv\Scripts\python.exe`.

## Environment & data
- Ephemeral cloud container: resets to an **older commit** and **wipes gitignored `data/`**. **GUARD: after a reset, `git fetch origin <branch> && git reset --hard origin/<branch>` and verify HEAD BEFORE reasoning about code — a stale checkout made me misstate update.bat more than once (e.g. "it doesn't run the audit", when it does).** This
  container usually has only a tiny sample rijal; the **user uploads** real files (e.g. the full
  `data/rijal.jsonl`) when a measurement needs them.
- turath.io is often **unreachable from here** → can't rebuild the corpus in the container; the user
  runs heavy steps on their machine. Catalog cached at `data/raw/turath/catalog.json`.

## Conventions (do these)
- **Reply to the user in ITALIAN** (domain terms stay Arabic).
- **Develop on the feature branch, then MERGE TO MAIN via PR.** `update.bat` pulls `main`, so a fix
  stranded on the branch never reaches the user (this caused real "why is the audit identical?"
  confusion). The user has approved this merge-to-main workflow. We **squash-merge**.
- **After every squash-merge, REALIGN the branch** — squash rewrites history, so branch and main
  diverge and the *next* PR hits merge conflicts on re-edited files (CLAUDE.md/docs). Immediately run
  `git fetch origin main && git reset --hard origin/main && git push --force-with-lease origin <branch>`
  so work stays linear (cost me a real conflict-resolution once before I learned this).
- Branch: `claude/intelligent-bardeen-HAsrg` — **we stay on this ONE branch** (the user deleted all
  others on 2026-06-09; do not create new feature branches). Repo (MCP scope): `a7medhosny92-cpu/hadith-research-backend`.
  NB: this container can push but **cannot delete remote branches** (the git proxy hangs up on `--delete`);
  the user prunes from the GitHub UI.
- Tests: `PYTHONPATH=. python3 -m pytest -q`. CI also runs `node --check` on the `<script>` extracted
  from `index.html` — keep it valid JS. Update the in-app «المنهجية»/«البنية» pages when behaviour changes.
- **No model id / assistant identity** in commits, PRs, code, or any pushed artifact.
- Commit/PR trailer: use the CURRENT session's trailer (the harness supplies it); latest was
  `https://claude.ai/code/session_01Q4Em93bJfdgE2TVT3yeeXr`.
- Don't open PRs unless asked — except the approved merge-to-main of our own fixes.

## The rijal matching model (so I don't re-derive it)
Identify the narrator **from the chain before the bare name** (تمييز المهمل):
- `app/rijal/index.py` — folded ordered tokens (بن/ابن dropped, kunya unified); `candidates()`
  returns the full homonym set; **containment requires the matched name be the leading run** of the
  citation (not an ancestor buried in the nasab); **teknonyms** (أبو/أم) match a kunya citation only,
  never a bare ism; prefix preference.
- `app/rijal/canon.py` — chain-first: with >1 candidate, pick by graph company before the bare name.
- `app/qa/isnad.py` — an ambiguous match is usable only if its tied candidates **agree on the grade**
  (`grade_agreed`); else the chain is held (يُتوقَّف), never graded weak.
- `app/parsing/rijal_extract.py` — drops junk at parse time: truncated «… بن», generic «عبد الله»,
  **single-token** names, and **bare ism+father with the gravest verdict** (كذاب, no nisba/kunya/death).
- `scripts/audit_isnad.py` — flags P (Prophet graded), S (صحابي mid-chain), W (full name متروك/كذاب),
  A (مشترك). Grade-agreement gates S/W.

## Current work — KEEP UPDATED
**Focus:** cut wrong isnad verdicts in «التدقيق» by identifying the narrator from the chain.

**★ LATEST (2026-06-09, large session → #129).** Two arcs on main; user to run `update.bat` (and,
optionally, `build_rijal_llm`) then send the new W/S/A.
- **(A) Real-data fixes #117–#126** (each verified against the *source books*, not the tiny sample):
  isnād boundaries + terminal-صحابي gated on `reaches_prophet` + ح-seam (#117) · death-year≠age (#118)
  · Prophet-never-a-student graph guard (#119) · **century-from-طبقة (#122)** — ~74 % of تقريب death-years
  were a century off («من العاشرة مات سنة ست وثلاثين» = 236, not 36), recovered from the طبقة (suspect
  1663→110), which **unblocks the same-man dedup** · **راوٍ disambiguation (#123)** — «عمر»/«عبد الله» had
  shown ONE conflated man with a generation-mixed network (عمر الصحابي with a شيخ who died 180y later); now
  shows ALL candidates, and fixed the `candidates()` **>40 cap** that returned `[]` for exactly the commonest
  names (added `max_results`; canon keeps the 40 default) · per-narration chains in search + ضبط-in-names
  strip (#124) · **Companions graded by DESCRIPTION (#125)** — ابن عباس «ابن عم رسول الله», أبو سعيد «له
  ولأبيه صحبة», أنس «خادم رسول الله» were «غير معروف» → صحابي (+79; gated on *no* طبقة) · **enmity ≠ كذاب
  (#125)** — المهلب «من ثقات الأمراء … أعداؤه يرمونه بالكذب» → ثقة (a critic's own «رماه ابن معين بالكذب»
  still stands) · **hamza-tolerant grades (#126)** — مالك/الشافعي/أحمد «الامام» in al-Kashif (source drops
  the hamza) → ثقة.
- **(B) The LLM strategy #127–#129 — root-cause cure for regex's long tail.** `scripts.build_rijal_llm` does
  **FAITHFUL** extraction (transcribe/segment verbatim, every record validated against the source or
  rejected→regex, cached): `--mode rijal` → grades + the **شيوخ/تلاميذ network** the terse books drop;
  `--mode chains` → clean isnād/matn for the chains the regex leaks matn into. **Wired GATED into the
  pipeline** (`app/rijal/llm_source.py`): build_rijal merges it, **build_graph adds the network to
  `canon._pick`'s company** (the lever for the ~1,144 genuine homonyms), parse overrides the flagged chains.
  No files present → byte-for-byte the regex pipeline. *Discovered the regex is a long-tail bug factory:
  مالك بن أنس in al-Kashif came out of the regex with a truncated kunya, the network in the grade field, and
  no death year — the LLM gets it right + the network.* **The known-but-unfixed matn-leaks** («عائشة جاءت
  امرأة…», «في قوله تعالى ﴿…﴾», «قال فلان:»-start → 0 narrators) are the `--mode chains` target.

**Below = the earlier (pre-#117) state, kept for history.**

**Latest audit (user's, post matn-fix + تهذيب-graph, 89,520 chains · 10,519 rijal):**
**W 833 / S 5783 / A 39,312**. vs the prior run (W 838 / S 5641 / A 40,281): **A −969** (تهذيب company
+ cleaner isnads from the matn fix resolved ~969 «مشترك» to a specific man), W flat, S +142. Real but
modest — تهذيب enriched only **1860** narrators (the conservative "unambiguous رجال match only" rule
skips many). Earlier baselines: stale W 1724 / S 7689 / A 35237 → W 838 / S 5641 / A 40,281 (A *rose*
as confidently-wrong cases became honest «held مشترك»).

**Merged to main recently:** chain-first id; teknonym reverse-only; prefix preference; grade-agreement;
«عبد الله بن» drop (earlier PRs) · ancestor-in-nasab (#87) · `measure_dedup.py` (#87) ·
`sample_source.py` (#88) · single-token + bare-grave junk drops (#89: kills خالد=صحابي,
يونس بن محمد=كذاب, عبد الرحمن بن محمد=كذاب) · **matn-completeness fix (#102)** · **تهذيب network
extractor + volume-in-citations (#103)**. (User must `update.bat` — which pulls main — to apply them.)

**This session (2026-06-09) — landed on main, all with synthetic regression tests, suite green:**
- **#117 isnad structural fixes:** (1) the terminal-صحابي promotion is now gated on `reaches_prophet`
  — on a موقوف/مقطوع chain the last link need not be a Companion, so الأسود النخعي (تابعي ثقة) is no
  longer force-promoted to الأسود بن سريع الصحابي; أبو ذر still resolves صحابي via natural lookup
  (verified). (2) back-reference «بهذا الإسناد/بإسناده», hadith-number markers «م - ٢٣٤٥» and lone
  ramz letters no longer become narrator nodes. (3) action verbs (يخطب/يحدّث/يذكر…) are a soft matn
  boundary (stop unless a transmission verb follows). (4) a تحويل (ح) is a **route seam**: the man
  before and after it are no longer read as a link (`continuity`) nor used as each other's
  disambiguation company (`canon`/`muhmal`).
- **#118 رجال death-year vs AGE:** `_death_year` anchored on the «سنة» *followed* by a number, so
  «مات وهو ابن ٨٧ سنة» (aged 87) is no longer read as death-year 87 (which corrupted same-man dedup).
- **#119 graph anachronism guard:** the Prophet ﷺ is never a *student* — a mid-chain-parse «Prophet
  narrates from X» edge is dropped (cleans the company data `canon._pick` reads).

**Deferred — needs the user's real-data A measurement first:** `canon._pick` over-confidence (a unique
winner on a *thin, single-token* overlap, esp. a generic nisba) is the next target, but tuning it
blindly risks the resolution rate; decide the threshold AFTER the post-#117/#118/#119 `update.bat` A.
The container has only a tiny sample rijal + full scans hit exit 144, so this MUST be measured on the
user's machine.

**Matn extraction fix (2026-06-08, PR #102 → main):** user saw «detti non completi» — e.g. al-Mustadrak
ط الرسالة (book **1424**) #7514 «ادع تلك الشجرة» showed matn=«ادع تلك الشجرة» (17 chars) with the whole
story dumped into the isnad (which ended at «قال: فقال»). Cause was `split_isnad_matn`: the *quote*
strategy took only the first quoted span and stopped at a >40-char narration gap. Fixes in
`app/parsing/isnad_matn.py`: (1) cross the **narration between dialogue quotes** of one story (stop
only at an editorial/takhrij marker or >220 chars); (2) `_story_start` — when the first quote sits
inside a post-chain **story** «أنّ رجلًا أتى النبيّ ﷺ … قال … فقال:» (≥2 spoken turns, *no* nested
سمع/حدثنا/عن link), start the matn at the «أنّ»; (3) `_trim_grade_tail` — drop a trailing al-Ḥākim /
Tirmidhī grade or takhrīj («هذا حديث صحيح…», «على شرط…», «وفي الباب…»). Verified vs old over all books:
**2034 matns improved, ~88 editorial tails trimmed, 0 real matn lost** (Bukhārī #1 / Muslim #95 stay
correct). NB: parse + index are FULL rebuilds, so this propagates on the user's next `update.bat`.

**Root-cause inventory of remaining flags (diagnosed on the real rijal):**
- *Stale audit*: top W/S repeats (عثمان بن أبي شيبة ×~80, عبد الله بن محمد ×~50, أبي إسحاق, أبو أسامة)
  already neutralised by grade-agreement → held as مشترك after rebuild.
- *Doppioni* (A): same man, two spellings across تقريب/الكاشف (الليث بن سعد, حماد بن سلمة, عبد الله بن
  وهب, ابن عقيل…); high audit impact because high-frequency.
- *Genuine homonyms* (A): different men sharing a stem (نصر الجهضمي الكبير/الحفيد, معمر, يحيى بن سعيد)
  — correctly مشترك; only context resolves them.
- *Grade-extraction bugs* (open): الحسن بن مدرك «كذاب خ س ق» (text says لا بأس به); سعيد بن أبي سعيد
  المقبري resolves to a مجهول truncation.

**Dedup measurement** (`measure_dedup.py` on the real 10,371-entry rijal, prudent rule):
**328** removable same-man duplicates · **1245** confirmed-homonym keys · **350** undecidable for
want of death-year/kunya (a richer source would settle them).

**Same-man dedup — BUILT (`app/rijal/dedup.py`, on branch, validated on the user's real rijal):**
Audit diagnosis showed ~half of «مشترك» (A) is the SAME man written two ways across تقريب/الكاشف
(هشام بن عمار, الليث بن سعد, يزيد بن هارون — high-frequency, so a few dups cause thousands of A flags);
`merge_source` couldn't unify them (lookup is containment-only; differing tails miss) and kept both.
`collapse_duplicates` collapses them after the source-merge. **Name rule:** same ism+father, lineage-
compatible (the nasab chains agree on every shared ancestor — «عبد الله»≠«عبد الواحد», «بن يونس»≠«بن
محمد»), shared specific nisba (no generation/strong-grade conflict) OR death(±20)/kunya. **+ corpus
veto (the user's idea):** `CorpusCompany` reads the PREVIOUS run's `narrators.db`; the name *proposes*,
the chain company *vetoes* a merge it contradicts (disjoint شيوخ/تلاميذ — التنيسي vs التستري), absent
men trust the name (**mix** policy). Measured on the real rijal: name-only 806 merges (118 are graph-
contradicted homonyms!), **mix 725** (drops the 118 false, keeps 121 the graph can't see), strict 618.
Wired into build_rijal (loads the graph if present). NOT on main yet — pending the user's go-ahead +
the real A re-measure after rebuild.

**More رجال data sources (user: «dobbiamo cercare altri dati»):** to resolve the *remaining* A — genuine
homonyms (need more network), the 350 «unconfirmable» dedups (need death-years), the 427 «غير معروف»
(need coverage) — add prose sources. Turath رجال (cat 26) verified: **2170 الجرح والتعديل (ابن أبي حاتم)**
4229p · **1293 تهذيب التهذيب (ابن حجر)** 2775p · 1692 ميزان الاعتدال · 5816 الثقات (ابن حبان) · 96165 الثقات
لمن ليس في الكتب الستة · 12397 تاريخ الإسلام (death-years). **BUILT (`app/parsing/jarh_extract.py`, on
branch): الجرح والتعديل (2170)** — early, independent, multi-critic, **beyond the Six Books** = genuinely
new signal. Format: numbered head (boundary works), NO rumūz, network **without a colon** «روى عن…روى
عنه…» split on «و», verdicts in «قال فلان: …»; footnotes cut at «____». Sample coverage شيوخ 84% · تلاميذ
85% · verdicts 31%. Wired into `build_graph` (`_NETWORK_SOURCES = {3722, 2170}`, both via
`tahdhib_associations`) and added to `RIJAL_PROSE_BOOKS` + the `--priority` download. **NB تهذيب التهذيب
(1293) deferred:** it's ابن حجر's abridgment of al-Mizzī → SAME Six-Books men/network → low *new* value
for A (its worth is ابن حجر's verdicts, a later double-opinion job); and its heads are title-spans (no
number) → needs a different segmenter. **Next:** download 2170 on the user's machine (update.bat now
fetches it) → measure the A drop; then death-year/coverage sources for the other two gaps.

**تهذيب الكمال extractor — BUILT (`app/parsing/tahdhib_extract.py`, PR #103 → main):** parses the real
3722 → **~6,870 tarājim, books 92% · شيوخ 94% · تلاميذ 93% · verdicts 57%**. Key lessons (see
docs/TAHDHIB.md): the book is heavily vocalised → every marker regex is diacritic-tolerant
(`flexible_word`) and grade words are matched diacritic-folded; minor narrators use the abbreviated
**«عَن:» / «وعَنه:»** (not «رَوَى عَن:») — colon required so chain «عَنْ» isn't mistaken; no
`indexes.numbers` so the محقق's ~200-page intro is skipped via a dense-rumūz-run heuristic
(`_muqaddima_skip`). Weak spots: ~14% names absorb bio, `death_year` ~19% (misses vocalised
spelled-out years), noisy verdicts. **Wired into `build_graph` (PR #104 → main):** `app/rijal/tahdhib.py`
turns each tarjama into an association (رجال canonical name → tokens of his شيوخ+تلاميذ, only when he
resolves unambiguously); build_graph merges these into pass-1 `profiles` when `3722.json` is on disk,
so `canon._pick` weighs al-Mizzī's authoritative company to resolve «مشترك» names — gated, no new
pipeline step, no regression if the book is absent. Activates on the user's next `update.bat`; measure
the A/«مشترك» drop after that. **Still to do:** feed multi-critic verdicts as a rich rijal source
(double-opinion); add تهذيب edges to the graph adjacency for `/narrator` display; polish death/تلاميذ/
long-names. Prudent same-man merge rule (for dedup): death-year ±~20 OR identical kunya; nisba/
generation conflict blocks the merge.

**⚠️ Per-volume page numbering (app-wide, user-flagged 2026-06-08 — FIXED PR #103):** many turath
books are multi-volume and **reset `page` to 1 each volume** (تهذيب has 35; al-Mustadrak's printed
«204» occurs 35×), so a citation needs **`vol` + `page`**, never `page` alone. Done: a single
`citeOf()` in `index.html` renders «collection · رقم N · ج V · ص P» for search cards, report variants,
copy-all, takhrij narrations, isnad source, audit case detail; `volume` saved into notebook chips and
added to the takhrij narration dict (`app/qa/takhrij.py`). Number-only audit citations left as-is
(رقم is unambiguous). **Keep this rule for any NEW citation surface.**

**Waiting on the user:** run `update.bat` **to completion** (step 2 pulls main → applies **#117–#129**;
then parse+index+rijal+graph+audit rebuild, so all the source-verified fixes — death-year century,
Companions-by-description, hamza-imam, disambiguation, etc. — land everywhere and the dedup unblocks)
→ send the new **W/S/A** from «التدقيق» for the true post-fix numbers. **Optionally first** run
`scripts.build_rijal_llm --mode rijal|chains` (with a configured engine) to produce the LLM rijal+network
and clean chains, which `update.bat` then auto-folds in (gated) — compare W/S/A regex-vs-LLM. Those
numbers gate the next move (`canon._pick` threshold tuning; wiring the LLM network display into `/narrator`).

## App cleanup / UX — TODO (user asked to remember, 2026-06-08)
The user runs **update.bat-only** and is overwhelmed by the pile of single-step launchers («perdo il
filo»). Each old launcher is just ONE step that `update.bat` already chains:
- `audit.bat` (tracked) → the audit step · `update-semantic.bat` (tracked) → `update --semantic`
- `AGGIORNA_GRAFO` (local) → build_graph · `RICALCOLA_SEMANTICA` (local) → embed
- `AVVIA_APP` / `AVVIA_FINESTRA` (local) → **launch the app** (`app.desktop` window / browser). NOT
  redundant — update.bat does not launch the app, so keep one of these.

**Semantic search is ACTIVE** on the user's machine (`data/vectors.db` ≈ 346 MB), so `update.bat`
already re-embeds every run (the «+ semantic» step fires because `vector_index_path.exists()`).

**Cleanup to do next:** consolidate to one update tool. If we retire the redundant standalone
launchers (`audit.bat`, `update-semantic.bat`), we MUST also fix the docs that reference them:
`README.md:144` («double-click update-semantic.bat …») and `app/static/index.html:1277` (the
audit-not-built fallback says «double-click audit.bat» → should point to `update.bat`, which now
builds the audit). Consider an in-app «update» button and/or a Windows scheduled task (the user
asked for hands-off updating).

**Gotcha (seen 2026-06-08):** the user's `update.bat` had stalled mid-flight at build_graph (~15:30):
index/sharh rebuilt (15:2x) but narrators/rijal/vectors/audit still 12:xx, with `_chains.tmp.jsonl`
left over. So «التدقيق» looked stale even though update.bat *does* run the audit — it just hadn't
reached that step. Fix = let `update.bat` finish (or re-run; it resumes).
