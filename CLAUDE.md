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
  confusion). The user has approved this merge-to-main workflow.
- Branch: `claude/intelligent-bardeen-HAsrg`. Repo (MCP scope): `a7medhosny92-cpu/review-backend`.
- Tests: `PYTHONPATH=. python3 -m pytest -q`. CI also runs `node --check` on the `<script>` extracted
  from `index.html` — keep it valid JS. Update the in-app «المنهجية»/«البنية» pages when behaviour changes.
- **No model id / assistant identity** in commits, PRs, code, or any pushed artifact.
- Commit/PR trailer: `https://claude.ai/code/session_01VLkYQkpBnrRwA5Wgu3UBB8`.
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

**Latest audit (user's, 2026-06-08 11:04 — STALE, pre the latest fixes):** ~84.9k chains ·
~10,463 rijal · **W 1724 / S 7689 / A 35237**. Re-run after rebuild for true numbers.

**Merged to main recently:** chain-first id; teknonym reverse-only; prefix preference; grade-agreement;
«عبد الله بن» drop (earlier PRs) · ancestor-in-nasab (#87) · `measure_dedup.py` (#87) ·
`sample_source.py` (#88) · single-token + bare-grave junk drops (#89: kills خالد=صحابي,
يونس بن محمد=كذاب, عبد الرحمن بن محمد=كذاب).

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

**Active next step — تهذيب الكمال (ROADMAP #8):** anchor on al-Mizzī (the source the others derive
from) for full names + **شيوخ/تلاميذ** (authoritative narrator network → resolves the 1245 genuine
homonyms at verdict time) + **multi-critic verdicts**. Plan = "study first": user samples real
tarājim with `sample_source 3722` and sends them; then design the prose extractor against real text.
Prudent same-man merge rule: confirm by death-year ±~20 OR identical kunya; nisba/generation conflict
blocks the merge.

**Waiting on the user:** run `update.bat` **to completion** (it rebuilds rijal AND regenerates the
audit — the last run stalled mid-flight, leaving stale numbers) → send the new W/S/A from the
«التدقيق» tab; and `sample_source 3722` samples of تهذيب الكمال.

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
