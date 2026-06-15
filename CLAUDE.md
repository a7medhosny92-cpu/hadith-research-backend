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
- **`python -m scripts.build_rijal_llm --mode rijal|chains [--model ID|--engine local|remote] [--sample N] [--dry-run]`**
  → **LLM-assisted, FAITHFUL** build-time extraction (the regex's long-tail cure). `--mode rijal` →
  `data/rijal_llm.jsonl` (grade + **شيوخ/تلاميذ network** + death/kunya the terse regex drops);
  `--mode chains` → `data/chains_llm.jsonl` (re-segment isnād/matn only for chains the regex flags
  suspicious). The LLM only **transcribes/segments verbatim**; every record is **validated against
  the source and rejected** (→ regex fallback) otherwise. Cache by hash; `--dry-run`/`--sample` to
  preview. **`update.bat` runs it automatically when an LLM engine is configured** (`llm_default_engine
  != off`, mirroring auto-semantic — `--llm`/`--no-llm` force it; the step is **non-fatal** so a missing
  engine/book never breaks the update), then **auto-folds the output in** (GATED → absent = pure regex
  pipeline): `build_rijal` merges the rijal, `build_graph` adds the network to `canon._pick`'s company,
  `parse` overrides the flagged chains. See `app/rijal/llm_source.py`.
  **Model:** a bare invocation (and `update.bat`) use the dedicated **`llm_extract_model`** (default
  **`ollama/qwen2.5:3b`** — LOCAL, free, offline, fast (direct-answer instruct, NO chain-of-thought — best
  for the big batch), NO weekly cap; the Ollama-Cloud free tier caps the whole ACCOUNT, which is why
  `gemma4:31b-cloud` hit «weekly usage limit» mid-update on 2026-06-11. `_parse_json` also strips a
  `<think>…</think>` block (reads only what follows `</think>`, else the scratchpad braces corrupt the JSON
  match), so a reasoning model like `qwen3.5:4b` works too — just slower. For the fast cloud extractor set
  `LLM_EXTRACT_MODEL=ollama/gemma4:31b-cloud`).
  `--engine local|remote` borrows the /ask brain (`llm_local/remote_model`); `--model ID` pins any litellm id
  (precedence `--model` > `--engine` > `llm_extract_model`).
- **`python -m scripts.audit_isnad`** → rescans all chains → `data/audit.json` (the «التدقيق» tab).
  **Run by update.bat as its final step** (so a plain update refreshes W/S/A); also runnable standalone.
  audit.json also carries **`a_ranked`** = the «مشترك» names ranked by how often they're ambiguous (+ candidates);
  the «التدقيق» A section renders this list (high count on a SPECIFIC name = over-match bug; famous-among-many =
  honest homonymy) with a **«قارن»** button → the «راوٍ» tab to compare the candidates (grade·death·nisba) side by side.
- **`python -m scripts.audit_matn`** → rescans every matn → `data/matn_audit.json` (the «تدقيق المتون» tab):
  flags V (empty/fragment) · I (isnad-in-matn) · G (grade/takhrij tail) · Q (verse/heading). Logic in
  `app.parsing.matn_audit.flag_matn`. **Also run by update.bat** (after audit_isnad); runnable standalone (needs
  only `index.db`, seconds). Built 2026-06-11 to «verify every matn». **Surfaced in the app as the «تدقيق المتون»
  tab** (`/matn-audit` endpoint, `renderMatnAudit` — shows each flagged matn + the reason + citation; with
  **V/I/G/Q filter chips** (`drawMatnAudit`, redraw without refetch) + a **«نسخ القائمة»** copy of the current filter).
  **★ V was 94% EMPTY matns (~1299, NOT truncations)** — diagnosed via the new **`scripts.peek_matn`** (read-only:
  dumps each empty-matn row, whose `isnad` column holds the WHOLE text, + the boundary markers split saw): the
  body was introduced by **«أنّ/أنّه/أنّها» with NO «قال»** («عن نافع أنّ ابن عمر كان…»، «عن رسول الله ﷺ: أنّه
  توضّأ») which `_ANNA` (only أنّ+النبي/رسول) dropped, or by a **quote right after «النبيّ ﷺ:»** with no قال. **FIXED
  in `split_isnad_matn`** with two **LATE fallbacks** (`"anna"` + `"authority"`, run only when every strategy fails →
  can't regress a working split): split at the first post-isnad «أنّ» that isn't itself a link («أنّ فلان أخبره»),
  else take what follows the terminal authority — both leaving al-Ḥākim's back-references («وأما حديث…»، «بمعنى…»)
  matn-less. +5 tests, 349 green. **NEEDS A RE-PARSE to apply** (split runs at parse time).
  **★ MEASURED (re-parse done, clean 86,391):** **V 1384→464 (−66%) · empty 1299→284 (−78%, ≈1015 matns recovered &
  now searchable) · I 2641→2011 (−24%) · G 563→286 (−49%)**. I/G fell too because the wrapper's route-peel now
  SUCCEEDS when the leaked inner body is «أنّ»-introduced (folds the route back → no longer «isnad-in-matn»);
  verified «حدثنا … عن نافع أن ابن عمر كان يتوضّأ» → matn «أن ابن عمر كان يتوضّأ» CLEAN (was I). Residual V 464 =
  genuine back-references + truncated sources + short legit answers («نعم»); I 2011 = «قال X: حدثنا [route]» +
  secondary-صحابي «حدّثني [صحابي] أنه شهد» (LLM `--mode chains` territory).
  **★ I-LEVER FIX (the dual «قالا»):** the dominant I (≈⅓, esp. Ibn Māja «ا: حدّثنا [route] أنّ النبيّ ﷺ
  matn») was `_SAY`'s bare «قال» matching the «قال» INSIDE the dual «قالا:» of «حدّثنا A وB قالا: حدّثنا
  [route]» — it split there, the leftover «ا:» blocked the route re-peel, and the whole secondary chain
  stayed in the matn. Fix: anchor `_SAY` to a word END (`(?![ء-ي])`) so «قال» never matches «قالا/قالوا/
  قالها»; the route then folds back and `_ANNA` recovers the body. +1 test, 350 green. **Needs a re-parse.**
  Residual I after this = standalone back-reference chains «حدّثنا X عن Y مثله/نحوه» (corroborating isnads,
  honestly matn-less — an exception candidate, not an error) + al-Bukhārī mu'allaqāt «وقال فلان: حدّثنا…» +
  a few false positives («جبريل أخبرني» = the Prophet quoting — flag_matn's `_CHAIN_VERB` is unanchored).
  **★ I/G PRECISION (audit-side, `flag_matn`, no re-parse):** the I residual was ~½ FALSE POSITIVES —
  back-reference chains (excepted now via the existing `backref` flag) and a chain verb DEEP in a complete
  matn (reported speech «هذا جبريل أخبرني»، Bukhārī muʿallaq tails). Fix: anchor the I chain-verb check to the
  matn HEAD (`mn.split()[:2]`) + add `not backref`; and guard G's `_EDITORIAL` so «أخرجه الله»/«رواه عنه»
  (real body) aren't takhrīj. Real head-leaks («ا: حدّثنا [route]») + «عن فلان»-start still flag. +3 tests,
  353 green. **★ MEASURED (audit-only re-run):** **I 1930→371 (−81%) · G 286→269 · V/Q flat.** ★★ MATN ARC
  SETTLED vs the very first audit: **V 1384→479 (−65%) · empty 1299→299 (−77%) · I 2641→371 (−86%) · G
  563→269 (−52%)** — ~5,000→~1,257 flags, residual = legit (short answers «نعم/لا», back-refs, verses, real
  takhrīj) or LLM `--mode chains` territory (the hard re-segmentations). The «detti non completi» are resolved.
- **`python -m scripts.measure_dedup [--input f.jsonl]`** → read-only: how much of «مشترك» is the
  same man twice vs genuine homonymy.
- **`python -m scripts.compare_company <name1> <name2> [...] [--top N]`** → read-only: dumps each homonym's
  شيوخ/تلاميذ (with counts) from `narrators.db` and the pairwise overlap (Jaccard + the distinctive, non-shared
  company), with a verdict — **DISTINGUISHABLE** (disjoint company → ②a, context CAN split them) vs **SHARED**
  (overlapping → ②b, the honest floor, held «مشترك» is correct). The tool for the ②a-vs-②b question (e.g.
  «سفيان بن سعيد الثوري» vs «سفيان بن عيينة» — do they have different تلاميذ?).
- **`python -m scripts.audit_conflicts [--cap N]`** → read-only: sweeps all رجال grouped by ism+father,
  finds **grave↔trustworthy name collisions**, and flags **DANGEROUS** (lookup confidently grades the grave
  → sinks a sound chain, the «كذاب في صحيح مسلم» class) vs **held** (ambiguous, correct) → `data/conflicts.json`.
  A clean run is DANGEROUS = 0; run after any rijal change to catch new collisions. **Wired into `update.bat`**
  (after audit_isnad/audit_matn) and surfaced in the app as the **«تعارض الرجال» tab** (`/conflicts` endpoint).
- **`python -m scripts.sample_source <id> [--entries N|--find "name"|--pages A-B] --out f.txt`** →
  read-only sampler to study a *prose* rijal source before writing its extractor; downloads the book
  if absent; never touches rijal.jsonl. Ids: تهذيب الكمال 3722, تهذيب التهذيب 1278(دبي)/1293(الرسالة).
- **`python -m scripts.find_book [title…]`** → read-only: find a turath book **id by title** from the cached
  catalog (`data/raw/turath/catalog.json`), printing ready «--books <id>» lines for `scripts.ingest` — so we pick
  a new رجال source without dumping the ~2 MB catalog into chat. Default args = the رجال/صحابة shortlist.
- The user runs everything on their PC with `.venv\Scripts\python.exe`.

## Environment & data
- Ephemeral cloud container: resets to an **older commit** and **wipes gitignored `data/`**. **GUARD: after a reset, `git fetch origin <branch> && git reset --hard origin/<branch>` and verify HEAD BEFORE reasoning about code — a stale checkout made me misstate update.bat more than once (e.g. "it doesn't run the audit", when it does).** This
  container usually has only a tiny sample rijal; the **user uploads** real files (e.g. the full
  `data/rijal.jsonl`) when a measurement needs them.
- turath.io is often **unreachable from here** → can't rebuild the corpus in the container; the user
  runs heavy steps on their machine. Catalog cached at `data/raw/turath/catalog.json`.
- **★ SHARED GOOGLE DRIVE FOLDER (the user's, persistent across sessions — CURRENT link re-given
  2026-06-12, REPLACES the older 1CFX4… one):**
  https://drive.google.com/drive/folders/1Jbj-bZ4FGi6Kq0HZwrzYgGYadBkDyJhP — the user drops the
  real measurement files here (`rijal.jsonl`, `audit.json`, `matn_audit.json`, `muhmal.json`, books).
  **Fetch them via the `Google_Drive` MCP** (`search_files` by title → `download_file_content` by id),
  so a session can pull the latest data WITHOUT waiting for a manual chat upload. (Big files >~20 MB
  still blow up context as base64 — prefer the small audit/rijal JSON, not the 15-30 MB raw books.)

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
  from `index.html` — keep it valid JS.
- **★ STANDING RULE (user, 2026-06-12): keep the THREE in-app reference pages ALWAYS in sync with the code,
  every change as we go — never let them drift.** «المنهجية» (`METHODOLOGY` array — where each datum comes
  from + why it's trustworthy), «البنية» (`ARCHITECTURE` — the overview), «التقنية» (`TECH` — the exact
  implementation: modules, scripts, data files, endpoints, config, counts). Each behaviour/structure change
  updates whatever these need (new tab/endpoint/script, a changed algorithm, a count like rijal≈9.7k or
  ~350 tests). They are user-facing and the user audits them — a stale point is a real bug. Audited+realigned
  2026-06-12 (rijal 10.5k→9.7k, ~240→~350 tests, تهذيب/الجرح «future»→integrated, +the audit/conflict tabs,
  +endpoints /conflicts·/matn-audit, +build_rijal_llm/audit_matn/audit_conflicts, +the new split strategies).
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
**Focus:** cut wrong isnad verdicts in «التدقيق» by identifying the narrator from the chain — AND now also
verify every **matn** (the new «تدقيق المتون»).

**★★ (2026-06-15, THIS SESSION cont.) THE JOINT-RESOLVER DIRECTION — `app/rijal/resolve.py` core BUILT (gated,
unwired). The user's insight + the next architecture.** The user pushed a deep point: «the company that should
resolve a name is ITSELF in conflict» — `canon._pick` reads the flat token company of a name's RAW neighbours, but
those neighbours are themselves ambiguous (a bare «عبد الله» beside «سفيان» gives no signal), so the disambiguation is
CIRCULAR. Their proposed cure (which IS the classical «تمييز المهمل بالنظر إلى الشيخ والتلميذ»): ANCHOR at the terminal
صحابي (we can ID him — position + الإصابة), then resolve each ambiguous تلميذ by **who is DOCUMENTED (in تهذيب/الجرح/
الثقات) as a تلميذ of the resolved شيخ**, propagating UP generation by generation. **Why it beats `canon._pick`:** (1)
DIRECTIONAL — `tahdhib_associations` (tahdhib.py:37) FLATTENS شيوخ+تلاميذ into ONE undirected token bag, throwing away
the direction this method needs (the extractors DO keep `shuyukh`/`talamidh` separate — the data exists, we collapse
it); (2) ANCHORED + PROPAGATED — resolve the certain links first, feed the RESOLVED IDENTITY (not an ambiguous token
bag) forward as the constraint, iterate to a fixpoint; (3) IDENTITY-level — the constraint is a documented «تلميذ-of»
lookup, not a token overlap. **BUILT `app/rijal/resolve.py`** (PURE, isolated, NOT wired → zero risk): `DocumentedNetwork`
(per-man شيوخ/تلاميذ as `network_key` sets) + `resolve_chain(candidates, anchors, network)` → constraint propagation,
**POSITIVE-evidence only** (a documented homonym is selected; ABSENCE never rejects — the تلاميذ lists aren't exhaustive;
a non-unique survivor → held `None`, never guessed). +5 tests (سفيان→الثوري via الأعمش's documented students; mirror via
تلميذ; generation-by-generation propagation from ابن مسعود up; the honest floor held when neighbours are bare; conflicting
evidence held), node --check clean. **(2) DONE — the DIRECTIONAL network built + persisted.** `tahdhib.documented_students(records,
rijal)` → `network_key(شيخ) → {network_key(تلميذ)}` (resolves each man + his quoted شيوخ/تلاميذ to a رجال canonical name,
UNAMBIGUOUS only; populates from BOTH sides — a man's تلميذ gives `students[man]∋تلميذ`, his شيخ gives `students[شيخ]∋man`).
**Simplified to ONE dict** (mirror identity: «T شيخ of S» ⟺ «S تلميذ of T» ⟺ `S ∈ students[T]` → no separate teachers map →
half the file). `build_graph` now parses each `_NETWORK_SOURCES` book ONCE → builds the flattened company (canon) AND the
directional network → `resolve.save_network` → `data/documented_network.json` (`settings.documented_network_path`);
`resolve.load_network` reads it. +2 tests. **(3) DONE — WIRED into `analyze_isnad`** (`network=` param, gated): a chain-level
PRE-PASS builds per-link candidates (`candidates(apply_prominence=False, max_results=None)`) + anchors (a unique-name
`lookup`) → `resolve_chain(..., route_starts)` (respects ح seams). In the per-narrator loop it is the **LAST تمييز lever**,
fired only when `name == narrator.name` (muhmal+canon already gave up) → `name = joint[i]` → `record["resolved"]`; the طبقة
guards (deep-صحابي demotion, الإصابة) still run after, as a safety net. Loaded + passed in `audit_isnad` + the `/verify-isnad`
router (`_network()`). **Gated on the network file → ZERO overhead/change until `documented_network.json` exists.** +1 e2e
test (سفيان above الأعمش: no network → held «مشترك»; with the documented network → resolved الثوري, grade flows), **407 green**,
node --check clean. Docs: التقنية (build_graph + data files + the resolver card). **NEXT: (4) MEASURE.** **WAITING ON THE USER:
run `update.bat`** (build_graph generates `documented_network.json` — send its «N شيوخ» count to validate coverage) **then
`audit_isnad`** → expect **A to fall further** where a distinctive شيخ/تلميذ anchors the chain (سفيان→الثوري &c.), W/S stable
(the طبقة guards + positive-evidence-only). Caveat: the pre-pass adds per-chain `lookup`+`candidates` work → the audit may be
slower when the network is active (optimise only if needed). The honest floor (bare-flanked names, no documented network) stays A.
**Caveats (honest):** bounded by network COVERAGE (تهذيب الكمال = exactly the Six-Books men → good for the common case;
obscure men outside → no constraint → still floor); CASCADE risk → the seed anchors must be CONFIDENT (terminal صحابي +
unique-name), never override a confident specific match; the genuine floor (a man only ever flanked by bare names with no
documented network) remains — the goal is NOT A=0, it is «resolve what the text determines, hold the rest» (لا نختلق).

**★★★ (2026-06-12, THIS SESSION). الإصابة MEASURED → S REGRESSION DIAGNOSED + FIXED · الزهري-أخبره parsing
bug · the parsing-bug HUNTER (6 leak classes fixed). On main, branch `claude/intelligent-bardeen-HAsrg`. 380 tests green.**
The user ran `build_rijal --no-download` (الإصابة merged: **rijal 9,712 → 15,231, +5,519 صحابة**) + `audit_isnad`
+ `audit_conflicts`. Pulled the real `audit.json`/`rijal.jsonl` from the shared Drive (`data/` subfolder) and
decomposed them. Result — **الإصابة integrated cleanly (DANGEROUS still 0, W 656→641 ✓) BUT S EXPLODED 620→2528
(×4.1)** and A fell 83,835→76,845 (84,783 chains). **Diagnosed (reproduced in-container on a synthetic rijal):**
the +5,519 الإصابة Companions are NON-تقريب obscure men → their **bare ism+father** names («محمد بن عبد الله» ×4,
«حارثة بن محمد», «أنس بن أبي أنس», «عنبسة بن أبي سفيان»…) **exact-match a mid-chain citation and OUTRANK the real
تابعي containment-matches** → resolve UNIQUELY to صحابي mid-chain → false S **and** mask the real man's weakness
(verdict bug, worse than the flag). A↓ is the SAME effect (positions that were honest «مشترك» now resolve onto a
Companion). A nisba-gate is NOT enough (a nisba Companion «سعد بن مالك الساعدي» still containment-matches bare
«سعد بن مالك»). **FIX — obscure-Companion dictionaries are mid-chain-INERT** (`index.from_companion_dictionary`,
gated in `isnad.analyze_isnad`): a صحابي whose grade rests ONLY on الإصابة is usable at the chain's END (terminal /
penultimate صحابيٌّ عن صحابيّ) but DROPPED to unknown (`match=None`) DEEP (≤ terminal−2) — kills the false S + the
masking, KEEPS the benefit (an obscure terminal Companion is still identified). Note the match feeds `record["rijal"]`
directly, NOT via `usable`, so the fix sets `match=None` (not just unusable). +1 test. **Effective on the next
`audit_isnad` ALONE (no rebuild)** — analyze_isnad is called live. **★ MEASURED (user re-ran audit_isnad at `c889837`):
S 2528 → 596 ✓ (BELOW the pre-الإصابة ~620), W 642, A 76,578, DANGEROUS 0** — the regression is eliminated and the
+5,519 صحابة are kept (identified as terminal Companions). The الإصابة EXTRACTOR is UNCHANGED — the fix is at
match/verdict time, so the cards stay for the «راوٍ»/terminal use. الإصابة is now net-positive.
- **★ PARSING BUG (user screenshot) — «الزهري أخبره» as a narrator name.** `analyze_isnad._VIA` had `أخبرنا/أخبرني`
  but NOT the **object-pronoun forms** «أخبره/أخبرها/أخبرهم · حدثه/حدثها/حدثهم · أنبأه» — so in the FRONTED-شيخ
  construction «(أنّ) الزهري أخبره أنّ …» the verb glued onto «الزهري», forging a bogus graph node that aggregated
  al-Zuhri's whole network. (Curiously `isnad_matn._LINK_AHEAD` already knew this set — an inconsistency.) FIXED:
  added the forms to `_VIA` (سماع). `scripts.build_graph` segments with `analyze_isnad`, so the «راوٍ» node clears on
  the next **re-parse + build_graph** (`update.bat`); the audit picks it up live. +1 test.
- **★ «cercare tutti i bug di parsing» → NEW `scripts.audit_nodes`** (read-only, the segmentation counterpart of
  audit_isnad/audit_matn): re-segments every isnad, flags any finalised narrator node still carrying a non-name
  fragment, CLASSIFIED — **verb** (transmission/قراءة glued: «أخبره», «قرأت على» — the dominant class), **say**,
  **action** (كان/يخطب…), **anna** (أنّ glued), **backref** (مثله/بهذا الإسناد), **number** → `data/node_audit.json`
  + ranked summary. Zero false positives on real names (سمعان/قرة/علي/أبو بكر/the Prophet — tested). The object-pronoun
  «أخبره» class was found exactly this way; the detector enumerates the REST on the real corpus. +1 test (8 cases).
  **★ MEASURED + ALL 6 CLASSES FIXED (2nd PR):** the user ran it → **1,868 corrupted nodes (1,523 distinct)**:
  **verb 553** (قرات/قراه = «قرأت/قُرئ على» 321 · حدثتني/حدثكم/سمعوا/اخبرتني…) · **number 482** (footnote-superscript
  digits glued: «الله١», «حدثنا١», «م ٢») · **action 291** (كان 191 · رأيت/دخل/خرج/سألت) · **backref 274** (فذكر/فذكره/
  بمعناه) · **anna 263** (أنّهما/أنّهم — DUAL/PLURAL co-narrators «X وY أنهما حدثاه/سمعا») · **say 46** (فقالت/فقالوا/
  يقولون). Each = a missing boundary rule, all added to `analyze_isnad`: _VIA gains the 1st/3rd/plural + قراءة forms
  (+ a `_QIRAA` set whose following «على/عليه» is SKIPPED, never read as the name «علي»); _MATN_ANNA gains أنّهما/أنّهم/
  أنّهن; _MATN_HARD gains فذكر/فذكره/بمعناه; _MATN_VERB gains كان/رأيت/دخل/خرج/سأل…; _MATN_SOFT gains فقالت/فقالوا/يقولون;
  and tokens are **digit-stripped** before segmenting. Verified clean on all 6 synthetic classes + re-checked with the
  detector. +6 tests, **380 green**. **★ MEASURED (user re-ran both at `3504952`): `audit_nodes` 1,868 → 2** (only
  «سمعتها»/«أخبركم» — two more object/2nd-person pronoun forms, now ADDED to `_VIA` → next run = 0). **Cross-check
  `audit_isnad`: W 642→643 · S 596→598 · A 76,578→77,027** — W/S FLAT (the new matn-boundary rules did NOT truncate
  real chains, the worry didn't materialise), A +449 (+0.6%) BENIGN = cleaner names now match more (e.g. the قراءة
  split KEEPS «مالك» where «قرأت على مالك» was one junk node → recovered narrators land as honest homonymy). The
  parsing-cleanup arc is VALIDATED. **Caveat the metric can't see** (told the user): a node «clean» of junk can still
  be a waw-joined dual «ابن عباس وابن عمر» (two men in one) or a truncated chain — those are the residual, not 0.
- **★ أقوال الأئمة — NAMED multi-critic verdicts (user: «riportare anche i loro nomi»).** The رجال books are not one
  verdict but a dossier of NAMED judgements («قال ابن معين: ثقة، قال أبو حاتم: لا يُحتجّ به، ذكره ابن حبان في الثقات»);
  ابن حجر/الذهبي only distil them. The prose sources (الجرح 2170, تهذيب 3722, and the coming الثقات/لسان) report them with
  the names — but those fed only `build_graph` (network), so the names never reached the cards. NOW captured end-to-end:
  **`app/parsing/appraisals.py`** `extract_appraisals(body)` → `[{critic, verdict}]` (a curated نقّاد list so an isnad
  narrator isn't taken for a critic + a grade-word filter on free-text quotes; verb/inclusion verdicts are graded by
  construction; `normalize_for_search` so «أبو حاتم» folds; `_QIRAA`-free); the prose extractors (`jarh_extract`/
  `tahdhib_extract.parse_entry`) add `appraisals` to their records; **`build_rijal.merge_appraisals`** attaches them to
  the matching rijal entry by an UNAMBIGUOUS name match (grade unchanged, add-only, after dedup); `RijalEntry.appraisals`
  + to_dict/from_dict carry it; the «راوٍ» card shows **«أقوال الأئمة»** (`rijalAppraisals` in index.html). +5 tests,
  **385 green**, node --check clean. **NEEDS A `build_rijal` (update.bat) with 2170/3722 on disk to populate** (then the
  card fills). Docs: المنهجية «درجات الرواة» card + التقنية RijalEntry/appraisals. **NEXT:** every new prose extractor
  (الثقات/لسان) gets `extract_appraisals` for free → more names; consider widening the curated نقّاد list as we see misses.
- **★ الثقات EXTRACTOR (2026-06-15, THIS SESSION) — `app/parsing/thiqat_extract.py`, the first new COVERAGE source.**
  The user ran `peek_thiqat` and gave the probe (`thiqat_struct.txt`). **الثقات ممن لم يقع في الكتب الستة (ابن قطلوبغا,
  96165)** — men OUTSIDE the Six Books, to pull people out of «مجهول». Same PROSE format as الجرح → reuses jarh_extract's
  field helpers (`_SHU`/`_TAL`/`_block_between`/`_names`/`_verdicts`) + `extract_appraisals`. The difference الجرح doesn't
  do: it GRADES — the **weakest cited جرح/تعديل verdict** if any (الجرحُ المفسَّر مقدَّم — «في الثقات لكن قال أبو حاتم
  ضعيف» → ضعيف), else **«ثقة» by inclusion** (`_grade_from`). **Two real quirks handled** (seen in the probe): the name is
  often only in the **«N - Name» HEADING** not the body (which opens «. سمع وحدث…») → `_heading_names` map, heading wins;
  a dedicated `_NAME_END` for the PRESENT «يَروي» (jarh's past-tense «روى» left a dangling «ي») + a relational tail
  («أخو فلان / من أهل»); and a real-tarjama **SIGNAL gate** drops the محقق's numbered muqaddima book-list. Wired into
  `build_rijal` ADD-ONLY (`merge_source fill_gaps=False`, like الإصابة) + in the `merge_appraisals` loop (so existing men
  get الثقات's أقوال الأئمة too); `_ensure_downloaded` fetches 96165. **★ ALSO wired its شيوخ/تلاميذ into
  `build_graph._NETWORK_SOURCES`** (alongside تهذيب 3722 / الجرح 2170) so الثقات's company feeds `canon._pick` —
  the disambiguation lever the user asked for: a تقريب/الكاشف man who carries NO network becomes resolvable by
  الثقات's stated شيوخ/تلاميذ (cuts the «A = rete mancante» class, NOT the «A = compagnia condivisa» floor).
  `tahdhib_associations` is generic (reads name+shuyukh+talamidh), so it took only adding 96165 to the dict.
  +7 tests, **392 green**, node --check clean. Docs:
  المنهجية «درجات الرواة» + «الكتب والمصادر» (الثقات now integrated) + التقنية build_rijal. **CAVEATS to measure** (told the
  user): the book is alphabetical & MIXES eras (early تابعون beside 6th-c. men with biographical not-جرح notes → graded
  «ثقة» by inclusion, slightly generous); a الثقات «ثقة» with a common name could over-match mid-chain like الإصابة did
  (but ثقة, not صحابي → no S, at most A) → **WAITING ON THE USER: `build_rijal --no-download`** → send «merged الثقات:
  +N ثقات» + the grade distribution + an `audit_isnad` (watch A/W). **NEXT extractors:** الثقات 5816/5825 (ابن حبان/العجلي
  direct) → لسان الميزان 36357 (the weak non-Six) → الطبقات 9351.
- **★★ MEASURED → الثقات A-REGRESSION DIAGNOSED + FIXED (the «coverage shadows the famous» bug).** The user ran the full
  sequence (`build_rijal --no-download` → `build_graph` → `audit_isnad`) at `1bbf13a`: **rijal 15211 → 19951** (+4789 ثقات,
  +5511 صحابة earlier, +1117 أقوال الأئمة attached, الثقات network merged for 4966), **W 624 ✓ but A 83303 → 88570 (+5267)**.
  Decomposed `a_ranked`: the top is the FAMOUS names — **أبي هريرة ×5937, سفيان ×4937, معمر ×2225** — and the `candidates`
  showed WHY: «أبي هريرة» = `عبد الرحمن بن صخر الدوسي` (the real Companion) tied with `محمد بن أيوب الواسطي`/`محمد بن فراس الضبعي`
  (obscure الثقات men who merely CARRY the kunya «أبو هريرة»); «معمر» = `ابن راشد` drowned by ~7 obscure معمر. So coverage
  (الإصابة 5511 + الثقات 4789) **polluted the candidate sets of the commonest names/kunyas** → the famous narrator no longer
  resolves → A exploded. NOT honest homonymy — a REGRESSION (أبو هريرة, the most recognisable Companion, made «مشترك»).
  **FIX (`index._prefer_non_coverage`, in `_lookup`'s tied-group computation, both contained & partial):** a coverage-only
  man (`from_coverage_source` = الإصابة/الثقات source) is DROPPED from a tied candidate group when a non-coverage man is
  present — kept only when ALL are coverage (a genuinely non-Six-Books citation). «أبي هريرة» → الدوسي alone ✓; «سفيان» →
  عيينة/الثوري honest tie (أسد/أمية dropped) ✓; a sole coverage man still resolves ✓. **Effective on the next `audit_isnad`
  ALONE (no rebuild)** — it's in the live matcher. +1 test, **393 green**. Docs: التقنية lookup. NB this also distinguishes
  «A onesta» (سفيان عيينة/الثوري — both تقريب, kept) from «A rumore» (coverage namesakes — dropped). The «ابن عمر = عمر بن
  الخطاب (father)» case in the A top is the SEPARATE old «ابن X» eponym bug, not this. **WAITING ON THE USER: re-run
  `audit_isnad`** (no rebuild) → expect A to fall sharply back toward/below the pre-coverage level; send W/S/A + the new `a_ranked` top.
- **★★ MEASURED → the targeted patches WEREN'T ENOUGH → PROMINENCE PRIOR built (Fase B of the plan).** The user re-ran
  `audit_isnad` at `d502120` (#154/#155 coverage + #156 eponym): **S 787 → 487 ✓✓** (the coverage fix resolved terminal
  Companions — big win) BUT **A 84688 → 85184 (slightly UP)**, not the predicted crash. Decomposed `a_ranked`: أبي هريرة
  5937→5241 (the coverage fix helped −696, residual = SAME-MAN DUPLICATES «عبد الرحمن بن صخر الدوسي» = «أبو هريرة الدوسي»,
  a dedup gap), and **ابن عمر 2372→3417 + ابن عباس new 2265** — the eponym fix #156 BACKFIRED on A: removing the father
  exposed the «many sons» (عبد الله/عبيد الله بن عمر…) with nothing to pick the famous one. **The data PROVED the plan:
  targeted patches alone can't — the A residual is duplicates + many-namesakes, which only a PROMINENCE prior resolves.**
  **BUILT (`index._prefer_prominent`, applied after `_prefer_non_coverage` in both `_lookup` branches + `candidates`):** each
  name's corpus narration frequency (`graph.frequencies()` → the `narrator.freq` column) breaks a tie toward the prolific
  man — keep a candidate only if ≥ 1/4 (`_PROM_RATIO`) as prolific as the top, else drop. «ابن عمر» → عبد الله بن عمر (the
  prolific son); «سفيان» → عيينة/الثوري honest tie KEPT (both prolific — only context can split, the ②a-company floor). Wired
  via `RijalIndex.set_prominence()`, set from the loaded graph in `audit_isnad._build_canon` + the app's `verify_isnad._canonicalizer`
  + the `/narrator` endpoint — so **effective on the next `audit_isnad` ALONE (no rebuild)**, the graph is already loaded.
  +1 test, **396 green**, node --check clean. Docs: التقنية lookup. **WAITING ON THE USER: re-run `audit_isnad`** → expect A
  to finally fall (ابن عمر/ابن عباس/the bare isms resolve); the honest floor in the A top = comparably-prolific pairs
  (سفيان عيينة/الثوري) → those need the company (②a, sub it via more network). Also TODO: dedup the same-man «الدوسي» pair.
- **★★ MEASURED → the prominence prior WORKS for A but EXPLODED S (a صحابي mid-chain regression) → FIXED with `apply_prominence`.**
  The user re-ran `audit_isnad` at `fa70bc9` (#157): **A 85184 → 61540 ✓✓ (−28%, the biggest A drop yet** — أبي هريرة and
  ابن عباس GONE from the `a_ranked` top; the residual top = سفيان 4937 / ابن عمر 3326 / معمر / محمد بن جعفر / يحيى, the
  comparably-prolific pairs that are the honest ②a floor) **BUT S 487 → 1794 (×3.7), a REGRESSION.** Diagnosed: the prominence
  prior, applied INSIDE `candidates()`, resolves a bare mid-chain «جابر» to the prolific **جابر بن عبد الله الصحابي** and
  DROPS the less-narrated تابعي **جابر بن يزيد الجعفي** from the candidate list — so the deep-صحابي demotion in `analyze_isnad`
  (which reads `candidates()` to find a non-صحابي homonym) no longer SEES the تابعي → can't demote → false «صحابي mid-chain».
  Prominence is right for the bare lookup (the famous man IS usually meant) but wrong for the demotion (which needs the FULL
  homonym set). **FIX (`index.candidates(apply_prominence=True)` flag):** the prominence filter is now gated; the deep-صحابي
  demotion calls `rijal.candidates(narrator.name, apply_prominence=False)` to see every homonym (including the obscure تابعي).
  Verified: DEEP «جابر» (سفيان عن جابر عن الشعبي …) → الجعفي ضعيف (no S); TERMINAL «جابر» (أبي الزبير عن جابر عن النبي) →
  الأنصاري صحابي (kept). **Effective on the next `audit_isnad` ALONE (live matcher).** +1 test, **397 green**, node --check clean.
  Docs: التقنية lookup. **WAITING ON THE USER: re-run `audit_isnad`** → expect **S to fall back from 1794 toward ~487-600 while A
  holds ~61540** (both A↓ AND S-stable = the prominence prior finally net-positive). Residual A floor = سفيان عيينة/الثوري &c. (②a,
  needs company); TODO still: dedup the same-man «الدوسي» pair (the أبي هريرة residual).
- **★ NEW TOOL for the ②a-vs-②b question — `scripts.compare_company` (read-only).** The user challenged the «سفيان عيينة/الثوري =
  floor» claim («questa omonimia non si risolve dalla compagnia?» — they have DIFFERENT تلاميذ) and asked me to check; I CAN'T (narrators.db
  is 12 MB, blows context as base64). So built `scripts.compare_company <name1> <name2>`: dumps each man's شيوخ/تلاميذ + the pairwise overlap
  (Jaccard + distinctive company) + a verdict (DISTINGUISHABLE → ②a, context can split; SHARED → ②b, true floor). +1 test, **398 green**.
  **WAITING ON THE USER: run `python -m scripts.compare_company "سفيان بن سعيد الثوري" "سفيان بن عيينة"`** → if their تلاميذ are mostly
  disjoint, سفيان is ②a (a company/relaxation target, NOT the floor I called it) and we wire that lever; if they share most company, ②b stands.
- **★★ MEASURED (#158 `apply_prominence` fix at `e48542a`) → S 1794→1067 (helped, NOT the ~500 predicted) → ROOT CAUSE = «عبد الله»
  + FIXED (the >40-homonym demotion blind-spot).** The user re-ran the three commits in sequence: #156 `d502120` **W 659 · S 487 ·
  A 85184**; #157 `fa70bc9` (prominence) **W 630 · S 1794 · A 61540**; #158 `e48542a` (the `apply_prominence=False` demotion fix)
  **W 628 · S 1067 · A 64350**. So vs the pre-prominence baseline the prior is **A −24% (85184→64350, the big win — أبي هريرة/ابن
  عباس/ابن عمر resolved & GONE from the A top) at a cost of S +580 (487→1067) and W −31**. My «S→~500» prediction was WRONG (owned it).
  **Decomposed `cases["S"]` (sample 500/1067): «عبد الله» = 297 (59%!)**, then a long tail (حميد بن عبد الرحمن 17, ابن جابر 15,
  عثمان 14, الحسن 8, الشعبي 7, محمد 7, …). **Root cause (reproduced in-container):** bare «عبد الله» has HUNDREDS of homonyms;
  `_lookup`'s prominence collapses them to the prolific bearers = the **four ابادلة (ابن مسعود/عمر/عباس/عمرو — ALL صحابة)** → a
  confident صحابي match mid-chain. The deep-صحابي demotion that should undo it calls `candidates(apply_prominence=False)` — but
  `candidates()` returns **`[]` for any name with >40 homonyms** (the display cap), so for the commonest isms (عبد الله/محمد/عثمان…)
  the demotion is BLIND and can't see the later تابعي «عبد الله» to demote to → false S. (Why «ابن عمر» did NOT regress to S: its
  prolific bearers are عبد الله الصحابي **and** عبيد الله العمري التابعي → grades DISAGREE → held A, not a confident صحابي.) **FIX
  (`isnad.py`, 1 line):** the demotion calls `candidates(..., apply_prominence=False, max_results=None)` so the >40-homonym set is
  NOT capped to []; it then sees the تابعي and demotes (→ held A / ثقة, never a mid-chain صحابي). Verified in-container: capped→0
  candidates (blind), uncapped→46 (sees the تابعي) → grade ثقة, no S. +1 test, **399 green**, node --check clean. **Effective on the
  next `audit_isnad` ALONE.** **WAITING ON THE USER: re-run `audit_isnad`** → expect **S to fall hard (the «عبد الله» 297-of-500 bucket
  → A), likely toward/below the 487 baseline, with A ticking up slightly (~65k)** = the prominence prior finally net-positive (A↓ AND
  S at/below baseline). Residual S tail to attack next: حميد بن عبد الرحمن/ابن جابر (small, 2-3-token — a different cause, NOT the bare-ism
  blind-spot) + legit صحابيٌّ-عن-صحابيّ (ابن عباس/ابن عمر, low counts).
- **★ سفيان MEASURED via `compare_company` (the user ran it) → MIXED, leaning ②a (the floor claim was too strong).** Output:
  الثوري freq 3474 (شيوخ 573 · تلاميذ 407) vs ابن عيينة freq 3227 (شيوخ 458 · تلاميذ 570). **تلاميذ Jaccard 0.14** (shared 120 ·
  only-الثوري 287 · only-عيينة 450), **شيوخ Jaccard 0.21** (shared 180 · only-A 393 · only-B 278) → verdict **MIXED — partially
  separable**. So the user was RIGHT to push back: سفيان is **NOT a pure ②b floor** — most of each man's company is DISTINCTIVE
  (الثوري←الأعمش/منصور/سلمة بن كهيل & →وكيع/عبد الرزاق/أبو نعيم; عيينة←الزهري/عمرو بن دينار/أبي الزناد & →الحميدي/قتيبة/ابن المديني),
  the ~14-21% shared is the genuinely-common teachers (هشام بن عروة, محمد بن المنكدر…) + a few students who took from both (وكيع,
  أبو نعيم, يحيى القطان, عبد الرزاق). **IMPLICATION:** when a سفيان sits in a chain WITH a distinctive شيخ or تلميذ, `canon._pick`
  CAN resolve it (②a — it's already the lever, just needs the company to be present/clean in that chain); only a سفيان flanked by
  the SHARED ~15% (or bare, no neighbours) is a true hold. So the A residual on «سفيان» is part ②a-recoverable (more network / the
  شيخ-only relaxation), part ②b. NB the dump also shows **dirty graph nodes** to clean later: waw-joined duals «وكيع وعبد الرحمن»
  (24×), «أبي الزناد وابن عجلان», truncations «عبد الله بن عبد», «عمرو بن» — these inflate the company sets and are the audit_nodes
  residual «two-men-in-one-node» class the metric can't see.
- **Docs:** المنهجية أعلام card (الإصابة «only at the chain's end, never mid-chain»), التقنية (analyze_isnad object-pronoun
  forms + الإصابة terminal-only; +scripts.audit_nodes→node_audit.json; ~350→~360 tests). node --check clean.

**★★ SESSION CONSOLIDATION (2026-06-11) — read this first; details in the dated entries below.**
**State: main = `e1ac017`, branch aligned (ff-merges, NOT squash), 344 tests green, all pushed.** This session
(measured on the user's real corpus, 84,807 chains · rijal 9,712):
- **S 1873 → 620 (−67%)** · **W 691 → 656** · **A ~flat 83,835** (A is honest structural homonymy — measured: al-Jarḥ
  network did NOT move it; we STOPPED chasing A's count, the wins are the wrong verdicts W/S). **Grave-shadow
  collisions DANGEROUS 2→0** (the «كذاب في صحيح مسلم» class closed + the permanent `audit_conflicts` watchdog +
  «تعارض الرجال» tab). **«غير معروف» 358 → 307** via the curated `companions.py` anchor.
- **Fixes landed (each verified on real data, tested):** name-compat S/W guard · ابن-X eponym · صحابيٌّ-عن-صحابيّ
  exemption · flipped-alias (المصلوب) · bare-grave hold · **X بن X collapse** · Companion-by-description +
  high-status anchor (Companions→صحابي, major Tabiin→ثقة) · qwen2.5:3b extract model + `<think>` strip · matn I/G ·
  the البنية Arabic diagram. **Bug-hunt sweep: the MATCHING is now clean** (collapse 0, self-match-failure 0,
  grave-shadow 0); what remains is extraction noise + the genuinely-obscure «مجهول».
- **★ IN-FLIGHT — DO NOT LOSE: the user is DOWNLOADING 10 رجال books to fill «مجهول»/coverage** (turath ids):
  **96165** الثقات-non-Six · **5816** الثقات-ابن-حبان · **1692** ميزان · **9767** الإصابة (Companions) · **36357**
  لسان-الميزان · **9351** الطبقات-الكبرى (+طبقة) · **1110** أسد-الغابة · **12288** الاستيعاب · **10490** معرفة-الصحابة-أبي-نعيم
  · **5825** الثقات-للعجلي. **NEXT = write an extractor per book** (like `jarh_extract`/`tahdhib_extract`) + wire into
  `build_graph`/`build_rijal`. **Order:** الإصابة 9767 (→ every صحابي out of «مجهول») → الثقات 96165/5816/5825 (→ثقة by
  inclusion + network) → لسان-الميزان 36357 (the weak non-Six) → الطبقات 9351 (broad + طبقة, also the A-lever). New
  helper **`scripts.find_book <title>`** locates ids from the cached catalog. **WAITING ON THE USER:** finish the
  downloads → «fatto» → I sample each format (via Drive / `sample_source`) and write the first extractor.
  **★ الإصابة EXTRACTOR BUILT (2026-06-12, `app/parsing/isaba_extract.py` + wired in `build_rijal`).**
  Key insight (from `scripts.peek_isaba` on the real book): `indexes.headings` (13,854) carries the WHOLE
  structure — every tarjama IS a heading («٨٢٠٣- مقسم بن بجرة») under its «حرف …»/«القسم …» headings — so the
  extractor reads HEADINGS ONLY (state machine: حرف opens at قسم 1; قسم heading switches; combined headings
  «الثاني والثالث» take the MOST RESTRICTIVE; the muqaddima never matches since it precedes the first حرف).
  **قسم I/II → {"name", grade:"صحابي"}; قسم III (مخضرمون)/IV (وهم) SKIPPED** (ابن حجر's own تمييز). Junk guards:
  single-token names (would containment-match every namesake), relational heads (امرأة من بني…/ابن…), «آخر» tags,
  bracketed footnotes. Wired GATED in `build_rijal` (after الكاشف, before LLM): **add-only `merge_source(...,
  fill_gaps=False)`** — a confident match to an EXISTING man is left untouched (populations differ: an obscure
  Companion sharing a Six-Books narrator's name must NOT stamp him «صحابي»); only genuinely-new names are added.
  `_ensure_downloaded` now also fetches 9767. +5 tests, 358 green. Docs updated (المنهجية أعلام card, التقنية
  pipeline, البنية improvements + SVG box «التقريب · الكاشف · الإصابة»). **WAITING ON THE USER:** run
  `build_rijal --no-download` (book already on disk) → expect «merged الإصابة (أقسام 1-2): +N صحابة» (N likely
  thousands) → then `audit_isnad` for W/S/A + the «غير معروف» count; full effect (graph company) on the next
  `update.bat`. **NEXT extractors:** الثقات 96165/5816/5825 (→ثقة by inclusion) → لسان الميزان 36357 → الطبقات 9351.
  **★ NOW SKIPPED FROM THE HADITH PARSE (2026-06-11):** once downloaded, `scripts.parse` read all 10 as hadith →
  **+26k bogus matn-less «hadith»** (V/empty exploded 1299→4312, scanned 86k→112k). FIXED by adding all 10 to
  **`RIJAL_PROSE_BOOKS`** (`app/ingestion/catalog.py`) so parse skips them (+ `_drop_stale` removes their stale
  `processed/{id}.jsonl`). They stay OUT of the corpus until their extractors land. **Needs a re-parse to clear.**
- **Also pending a `build_rijal`/`update.bat`:** the build-time fixes (`_COMPANION`, classify, `_drop_stale`, the
  matn re-split) only fully apply on a re-parse; the matcher/anchor fixes are LIVE (effective on the next `audit_isnad`).

**★ LATEST (2026-06-11, THIS SESSION cont.). 2ND-GRAPH RUN MEASURED → matn I/G fixes + graph-unlock LANDED ·
name-compatibility S/W guard added. On main, branch `claude/intelligent-bardeen-HAsrg`.**
The user ran a full `update.bat` (pulled main with the 7 regex fixes + the I/G matn fixes; 2nd graph rebuild;
LLM step skipped — gemma cloud weekly cap, non-fatal). New numbers, **84,807 chains · rijal 9,712 · مهمل 24,737**:
- **Isnad «التدقيق» — W 691 · S 1873 · A 83,717** (vs 5-fix run 686/2551/79,841). **S −26.6%** (the 2nd graph
  rebuild UNLOCKED the graph-lag → «أبي إسحاق»→السبيعي: confirmed in the uploaded rijal — السبيعي now
  «عمرو بن عبد الله … أبو إسحاق السبيعي» kunya «أبو إسحاق» · ثقة · †129, fix #2 «ويقال» recovered it). **A +4.9%
  is the other face of the matn I-fix**: the re-split puts the recovered route narrators BACK into the isnad →
  more (genuine-homonym) positions audited (honest holds, not mis-IDs).
- **Matn «تدقيق المتون» — V 1384 · I 2641 · G 563 · Q 124** (vs first run V1375/I4307/G651/Q121). **I −38.7%**
  (تحويل ح re-split) · **G −13.5%** (takhrīj-tail trim). Wins confirmed.
- **Decomposed the uploaded `audit.json`/`rijal.jsonl` (reproduced the matcher in-container on the real rijal):**
  - **S top now: «الحسن/الحسين بن علي + nisba» (الخلال †242, المعمري, بن زياد) ≈70/500** — late شيوخ ABSENT from
    the rijal whose distinguishing tail matches NO entry, so `candidates()` collapses them onto the bare 2-token
    leading run «الحسن بن علي» = the Companion grandson (الحسن بن علي بن أبي طالب, promoted صحابي by description)
    → graded «صحابي» mid-chain. **«أبي إسحاق» ≈59/500 residual** (kunya collision, was ~990, −78% via the unlock;
    canon still picks سعد in thin-company chains). «ابن عمر/عباس»/«أنس»/«محمود بن لبيد» = borderline-legit صحابي-عن-صحابي.
  - **A top = genuine homonymy** (علي بن محمد ×52 = 4 real men · محمد بن يحيى ×30 · سفيان عيينة/ثوري ×26) + **teknonym
    over-match** (أبي هريرة ×26 = the kunya pulls in 2 obscure محمد-named men beside الدوسي). The شيخ-only relaxation
    IS active (مهمل 24,737 ≈ 2×) but only resolves a BARE ISM by شيخ — it does NOT touch the 2-token homonyms
    («علي بن محمد») that dominate A. → A's lever is still context/coverage, not the relaxation alone.
  - **Matn I residual (2641): ~62% chain-verb-at-START** («حدثني [صحابي] أنه شهد… أنه نهى…» secondary-صحابي
    attribution — no «قال:»/quote, أنّ not «أنّ النبي» → re-split finds no boundary → **LLM `--mode chains` territory**);
    **~18% «قال [name]: حدثنا [route]»** (tractable next regex peel); **~5% false positives** («جبريل أخبرني» = the
    Prophet quoting, reported speech — flag_matn's `_CHAIN_VERB` is unanchored). **G residual (563)** partly AUDIT
    false-positives («أخرجه الله» — flag_matn's `_EDITORIAL` is unguarded, unlike the extraction trim). V (1384) =
    ultra-short answers («نعم»، «بعد الوضوء») — calibrate the word-count threshold.
- **★ FIX THIS SESSION — name-compatibility S/W guard** (`scripts/audit_isnad._name_compatible`, gates S & W):
  every content token of the CITED surface must appear in the MATCHED man's name (`_clean_tokens(cited) ⊆
  _clean_tokens(matched)`), else a more-specific namesake («الحسن بن علي بن زياد») is wearing a short Companion's/
  متروك's grade → don't flag. Validated on the real rijal (kills الخلال/المعمري/بن زياد; KEEPS «محمد بن سعيد بن
  حسان»→المصلوب كذاب and the deeper-ancestor «عبد الله بن عمر بن الخطاب»). **Est. ~150/500 S-sample suppressed**
  (≈ the الحسن/الحسين-بن-علي + concatenation-artifact class); +2 tests, 336 green. **★ MEASURED (audit-only re-run at
  `911ebb8`, name-compat ONLY — ابن-X not yet pulled): S 1873→1245 (−33.5%) · W 691→635 (−8.1%) · A 83,717 flat** —
  spot-on the estimate; the «الحسن بن علي + nisba» class is gone, A untouched (as designed).
- **★ FIX 2 — «ابن X» patronymic must not match the eponym** (`index._score_entry`, new `nasab_ref` param; gates
  the partial `offer`): a citation literally starting with «ابن»/«بن» means X is a FATHER, so a leading
  (ism-position) match is wrong. **«ابن عمر» matched 134 men NAMED عمر** (lookup picked عمر بن الخطاب the eponym,
  held مشترك) — now 0 عمر-led; «ابن عباس» same; reinforces the «ابن أبي مليكة» #3 fix; non-nasab citations
  («مالك بن أنس»، bare «عمر بن الخطاب») untouched. +1 test, 337 green. **HONEST scope: this is a CORRECTNESS fix
  (right candidates, and cuts «ابن X»→father-صحابي false S the name-compat guard misses because عمر∈«عمر بن الخطاب»)
  — it does NOT cut the A COUNT**: «ابن عمر» stays ambiguous among the *sons* (إسحاق بن عمر…), just no longer the
  father. **A's count-lever is NETWORK COVERAGE** (تهذيب 3722 / الجرح 2170 give `canon._pick` the شيوخ company to
  resolve «علي بن محمد» ×52 = 4 real men — تقريب/الكاشف carry NO network, so the dominant A is structural homonymy
  the relaxation can't touch). **WAITING ON THE USER: one `update.bat`** → send `audit.json` + W/S/A to measure the
  S drop (name-compat + ابن-X) and confirm A holds. **★ A-LEVER STATUS VERIFIED via the shared Drive
  (`data/raw/turath/`): تهذيب الكمال 3722 IS downloaded (`3722.json` 51 MB → its network already feeds `canon._pick`),
  but الجرح والتعديل 2170 is MISSING (only 2171 الكاشف present — a GRADES book, NO network; 2171≠2170). →
  downloading 2170 (the independent multi-critic network, `_NETWORK_SOURCES = {3722, 2170}`) is the remaining A
  lever; turath.io was unreachable when update.bat tried — retry until `2170.json` lands in `data/raw/turath/`. The
  container CANNOT fetch turath books (turath.io blocked); the user re-runs the download.**
- **★ al-Jarḥ MEASURED → the A NETWORK-LEVER is DISPROVEN.** The user downloaded 2170 (10.67 MB, complete),
  ran `build_graph` (log: «الجرح والتعديل company merged for **2,386** narrators» + تهذيب 1,824) + `audit_isnad`:
  **W 668 · S 1167 · A 83,793** (S −37.7% over the session ✅; A FLAT vs 83,717). Decomposed OLD vs NEW audit:
  the A top is **IDENTICAL** (علي بن محمد 52→51 · محمد بن يحيى 30→29 · أبي هريرة 26→26 · سفيان 26→26). → al-Jarḥ
  enriched BREADTH but did NOT touch the high-frequency homonyms that dominate A: they **share their شيوخ**, so
  `canon._pick` still ties → held. **A is structural homonymy + honest uncertainty, NOT a coverage gap** — the
  network lever (my hypothesis) is WRONG. Reducing A further = GUESSING (violates «لا يختلق»). → **stop chasing A's
  count**; the wins are W/S (wrong verdicts). al-Jarḥ still enriches the رجال cards + future double-opinion.
  S residual is now mostly **صحابيٌّ-عن-صحابيّ legit** (ابن عباس/عمر/أنس/محمود بن لبيد — the ابن-X fix now IDs the
  famous son correctly, which trips S): a precision refinement (extend the penultimate-link exception), not an error.
- **★ FIX — «flipped-name» aliases (a كذاب in صحيح مسلم!)** (`index._is_flipped_alias`, gates aliases in `add`):
  the user hit a SOUND Muslim chain graded «ضعيف جدًا» because «سعد بن سعيد» (سعد الأنصاري, a Muslim narrator)
  matched **محمد بن سعيد المصلوب (كذاب)** — the forger «قلبوا اسمه على وجوه», and one flip «سعد بن سعيد» was
  extracted as his ALIAS → an exact 2-token containment that OUTRANKS the real namesakes. Drop an alias whose ism
  differs from the entry's own (≥2 tokens, non-kunya) — 106/218 such aliases, ~all extraction noise (ضبط/fragments/
  stray verdict words). After: «سعد بن سعيد» → ambiguous (الأنصاري صدوق / المقبري لين) → HELD, not كذاب; المصلوب
  still reachable by his real name; kunya aliases exempt. Live in `RijalIndex.add` → effective on the next
  `audit_isnad` (no rijal rebuild). +1 test, 338 green. Expect **W↓** (fewer false كذاب/متروك). On main.
- **★ SYSTEMATIC CONFLICT SWEEP («controlla tutti i narratori, chi va in conflitto») + the bare-grave HOLD fix.**
  Swept all 9,620 rواة: grouped by ism+father (5,391 groups), found **67 grave-vs-trustworthy collisions**; of those
  **61 already correctly HELD** (ambiguous → the chain says «لا أدري» not a guess — RIGHT), 4 ok, and only **2
  DANGEROUS** (lookup confidently returns the grave → sinks sound chains): «إسحاق بن عمر» [متروك] & «يحيى بن عبيد»
  [متروك] — both a BARE 2-token truncated grave entry out-ranking a fuller trustworthy namesake (إسحاق بن عمر بن
  سليط الهذلي ثقة…). Only **3** bare-2-token grave entries exist (3rd = «أصبغ بن نباتة», a REAL متروك, no namesake —
  must NOT be lost). Fix in `index._lookup` (`_GRAVE` set): when the chosen CONTAINMENT match is grave AND fuller,
  better-graded partials also fit the bare citation → add them as alternatives → **HOLD (ambiguous, grade_agreed=
  False)** so the grade-agreement gate never grades the chain متروك. A lone grave (أصبغ — no namesake) still
  resolves. Re-swept: **DANGEROUS 2→0 · held 61→63.** Narrow (only fires for a grave contained match), live in
  `_lookup`, +1 test, **339 green.** → the rijal is now CLEAN of grave-shadowing conflicts; W should drop further.
  **Then made `audit_conflicts` permanent**: new read-only `scripts/audit_conflicts.py` (`sweep` + `_GRAVE`/`_TRUST`)
  → `data/conflicts.json`; **wired into `update.bat`** (after the isnad/matn audits) and surfaced as the app
  **«تعارض الرجال» tab** (`/conflicts` endpoint, mirrors `/audit`; `renderConflicts` in index.html) — a watchdog
  so the «كذاب في صحيح مسلم» class is caught in-app, not by accident. +1 test, node --check clean.
- **★ S #2 REFINEMENT — صحابيٌّ عن صحابيّ is legitimate at any depth** (`audit_isnad._flag_chain`): the S residual
  after name-compat/ابن-X is now mostly a younger Companion narrating from an older one («ابن عباس عن عمر»، «أنس عن
  أبي بكر») — NOT a misplaced صحابي. Extend the last-two-links exception: don't flag a صحابي whose own شيخ (the next
  link, `narrators[i+1]`) is ALSO a صحابي. Kept the guard tight: a صحابي whose شيخ is a non-Companion (تابعي) deep in
  the chain is STILL flagged (the real anachronism). Masking risk (a non-Companion mis-graded صحابي with a صحابي شيخ)
  is narrow — the residual صحابي resolutions are real Companions (ابن عباس→عبد الله بن عباس &c., verified). +1 test,
  341 green. Expect **S↓** (the صحابي-عن-صحابي class); measure on the next `audit_isnad`.
- **★ MEASURED on `094c3b2` (all session fixes live; the user's main was STUCK at a232e64 for several runs — the
  `git pull` MERGE kept aborting on a Windows-Defender lock of `.git/objects/00`; fixed with `gc.auto 0` +
  `git merge --ff-only origin/main`):** **W 656 · S 620 · A 83,835** (84,807 chains · rijal 9,712). **S 1167→620
  (−47% this run; −67% over the session from 1873)** — the صحابي-عن-صحابي exemption was the dominant residual (~547
  legit Companion-from-Companion). **W 668→656** (المصلوب alias + bare-grave — the «كذاب في صحيح مسلم» class closed).
  **A flat** (structural homonymy, honest uncertainty — settled). The wins this session are W/S (wrong verdicts);
  A is not chased. Residual S (620) = mostly real anachronisms (a صحابي with a تابعي شيخ) — genuine review cases.
- **★ FIX (A bug, user-screenshotted) — «X بن X» name-collapse** (`index._clean_seq`): the user saw «معاذ بن معاذ»
  held «مشترك» among ~20 unrelated معاذ. Cause: `_clean_seq` **de-duplicated** tokens, so «معاذ بن معاذ» (ism =
  father's name) folded to the bare «معاذ» → matched every معاذ بن فلان. Famous narrator (معاذ بن معاذ العنبري
  القاضي, ثقة) read as a 20-way ambiguity. Fix: keep an **adjacent** repeat (the «X بن X» pattern), still drop a
  non-adjacent one (a distant ancestor). After: «معاذ بن معاذ» → 1 candidate (العنبري, ثقة, not ambiguous);
  «محمد بن محمد» → the 7 real «محمد بن محمد X» (genuine homonymy, not every محمد). Live in matching → effective on the
  next `audit_isnad`. +1 test, 342 green. → part of A WAS a real bug (every «X بن X» narrator), now resolved; proves
  the screenshots are gold for separating A-bugs from honest homonymy.
- **★ BUG-HUNT SWEEP + the «مجهول → known» recovery (user: «cerca tutti i bug» / «molti noti sono ignoti»).**
  Systematic detectors on the real rijal: token-collapse = 0 (X-بن-X covered the class), self-match-failure = 0
  (no narrator's own name resolves to a wrong man — the grave/flipped/X-بن-X fixes closed shadowing), only 2
  truncated-name unreachables. → the MATCHING is clean; what remains is **extraction noise** (a few «بنمحمد»
  concatenations, 19 ضبط residuals, relational «صاحب/ابن عم الشعبي») and the **«غير معروف» class (358)**. Three
  user screenshots pinned the worst: **عبد الرحمن بن عوف** (أحد العشرة) read «مجهول» — his Companion bio leaked into
  the NAME, grade empty. Fixes: (1) `grades.classify` now reads Companion-by-DESCRIPTION («أحد العشرة، أسلم قديمًا،
  مذكور في الصحابة، بدري…») + the missing verdicts «متهم»→متروك, «ليس بالقوي»→لين; (2) `rijal_extract._COMPANION`
  gains the same; (3) **`RijalIndex.add` recovers** an ungraded entry: a curated CLOSED anchor —
  `app/rijal/companions.py` `MAJOR_COMPANIONS` (→صحابي) + `MAJOR_TABIIN` (the فقهاء السبعة، الزهري، الحسن، ابن
  سيرين… →ثقة) — else a POSITIVE grade leaked into the name (never a negative → can't sink a chain). **«غير معروف»
  358→307**: أبي بن كعب/عبد الله بن مسعود/معاذ بن جبل→صحابي, سعيد بن المسيب→ثقة; a GRADED namesake (عمر بن الخطاب
  السجستاني صدوق) is never overridden. +5 tests, 344 green. The remaining ~307 are genuinely-obscure or
  extraction-failed NON-famous entries → build-time re-extraction (most have a grade in تقريب; the empty = bugs).

**★ (2026-06-11, THIS SESSION). 5-FIX RUN MEASURED → the GRAPH-LAG throttle found · buried-ancestor
fix · MATN AUDIT built. On main, branch `claude/intelligent-bardeen-HAsrg` (HEAD `81d08db`).**
The user ran `update.bat` with the 5 fixes → **W 716→686 · S 2921→2551 (−12.7%) · A 82,394→79,841 (−3.1%)**;
**chains 90,549→84,807 (−5,742 = the 3722 garbage GONE, fix #5)**; **muhmal 12,052→24,391 (×2 = the relaxation's
`@`-keys, fix #1 active)**; rijal 9,786→9,723. Decomposed the uploaded rijal/audit:
- **The fixes bit at the DATA level (verified):** السبيعي recovered «… أبو إسحاق السبيعي», kunya «أبو إسحاق»
  (now a candidate of «أبي إسحاق»); **«ابن أبي مليكة» GONE from S (31→0)**; ضبط leak 810→31 (96%).
- **★ KEY FINDING — the one-iteration GRAPH LAG throttles the DATA fixes.** «أبي إسحاق» is STILL 180 in S because
  what *resolves* it at verdict is **`canon._pick`**, which reads the **graph company** (`narrators.db`), and
  step-7 `build_graph` built that graph from the **pre-fix rijal** (السبيعي still truncated there). So a
  **MATCHING** fix (#3 ابن أبي مليكة) acts immediately, but the **DATA** fixes (#1 relaxation, #2 السبيعي) need the
  graph rebuilt from the new rijal. → **the next measurement is a 2nd run (`build_graph → build_rijal →
  audit_isnad`)** — it unlocks «أبي إسحاق»→السبيعي and the relaxation's real A-drop. Smaller S still open: «الحسن
  بن علي بن زياد» (containment), «عثمان» (bare ism→صحابي).
- **Buried-ancestor fix** (`index.py::candidates`, `[81d08db]`): a COMPLETE name read «مشترك» with a
  descendant/nephew/longer-form whose nasab buries the query non-leading (محمد بن عبد الله بن جحش ← إبراهيم بن محمد
  بن… بن جحش; محمد بن مسلم بن شهاب الزهري ← ابن أخي الزهري). `candidates()` now drops a non-prefix partial when a
  containment match exists (the query IS a complete man); `lookup` was already right (NO audit change) — this
  cleans the «راوٍ» explorer + the chain candidate sets. A bare nisba «الزهري» still surfaces all its bearers.
- **★ MATN AUDIT — NEW subsystem** (`app/parsing/matn_audit.flag_matn` + `scripts.audit_matn`, `[61b5ae6]`): the
  متن counterpart of `audit_isnad`, to «verify every matn» (the user's directive). Scans every matn in index.db,
  flags **V** (empty/fragment + body-in-isnad — the «detti non completi») · **I** (a narration verb / leading
  «عن فلان» in the matn) · **G** (grade/takhrij tail) · **Q** (verse-only ﴿…﴾ or باب/كتاب heading) →
  `data/matn_audit.json` (the «تدقيق المتون» tab — **BUILT: `/matn-audit` + `renderMatnAudit`**). Wired into `update.bat` after the isnad
  audit. High-precision (إنما الأعمال بالنيات does NOT flag; al-Mustadrak #7514 «ادع تلك الشجرة» → V). V's
  word-count thresholds are the knob to calibrate on the real distribution.
- **★ FIRST matn_audit MEASURED + 2 regex EXTRACTION FIXES landed.** The user ran `scripts.audit_matn` →
  **V 1375 · I 4307 · G 651 · Q 121** (empty 1298), uploaded `matn_audit.json`, I decomposed it. **~93% clean.**
  Two systematic causes found + FIXED on main (so the next parse re-run shrinks them):
  - **I (4307) = تحويل ح leak** — the dominant I is a SECONDARY route («… ح حدثنا [route] … قال <matn>») left at
    the matn's HEAD by the first split. `split_isnad_matn` now **re-splits** (up to 3 peels) a matn that opens
    with a transmission verb, folding the route back into the isnad and recovering the body. `[302c42b]`
  - **G (651) = takhrīj/متابعة tail** — «رواه البخاري»، «أخرجه مسلم»، the dual «أخرجاه» the source appends after
    the body (al-Bukhārī/al-Ḥākim cross-refs; «هذا حديث/وفي الباب/قال أبو داود» were already trimmed). `_trim_grade_tail`
    now also trims these, **guarded** so real body survives («أخرجه الله من النار»، «من رواه عنه»): fires only on a
    sentence-opening cross-ref (after . ؟ ! » " ”) OR «رواه/أخرجه + collection name» OR the unambiguous dual. `[3de5805]`
**WAITING ON THE USER — ONE full `update.bat`** (`git pull` main first) measures BOTH open threads at once:
**(a)** the **2nd graph rebuild** (build_graph from the clean rijal) → unlocks «أبي إسحاق»→السبيعي + the
relaxation's A-drop → send the new **W/S/A** + `audit.json`; **(b)** the **matn re-run** (parse re-runs → applies
the I + G fixes) → re-run `scripts.audit_matn`, send `matn_audit.json` → I measure the I/G drop, calibrate V's
thresholds, attack the residual (LLM `--mode chains`), and add the «تدقيق المتون» UI tab.

**★ (2026-06-10, continued → THIS SESSION). FULL-CORPUS REBUILD MEASURED + the شيخ-only relaxation
validated on REAL data. Analysis + plan, NO code yet; on branch `claude/intelligent-bardeen-HAsrg`.**
The user ran `update.bat` to completion **with the LLM chains pass** (#142–#145 regex + LLM re-seg of the
flagged ~10%) and uploaded the real `rijal.jsonl` + `audit.json` + `muhmal.json`; I decomposed them in-container.
New «التدقيق»: **W 688 · S 2918 · A 82,678** (89,424 chains · 9,827 rijal) vs the pre-#117 baseline **W 833 ·
S 5783 · A 39,312**.
- **W↓ (−17%) and S↓ (−50%) are the #117–#145 WIN** — far fewer *wrong* verdicts (a متروك condemning the wrong
  man; a صحابي graded mid-chain). **A↑ (×2.1) is NOT a regression — it is honest holds of GENUINE homonymy.**
  Proof: `measure_dedup` on the real rijal = only **199 removable**, **1,109 confirmed-homonym keys**, 280
  unconfirmable → **dedup is not the lever**. The A sample (500) is concentrated on high-frequency names
  (علي بن محمد ×56, محمد بن يحيى ×31, سفيان ×30, أبو معاوية, الأوزاعي…), **0 garbage**, ~**88% genuinely held**
  (candidates disagree), ~12% grade_agreed. → **A is a COVERAGE gap, fixed by CONTEXT, not dedup.**
- **THE LEVER — شيخ-only relaxation, MEASURED on the real `muhmal.json`** (12,052 contexts, clean, ~85% add
  specificity): keying on `(bare-ism, شيخ)` instead of the exact `(تلميذ, شيخ)` → **6,165/6,809 (90%) resolve
  UNIQUELY**, and **5,731** of those resolve a globally-ambiguous bare ism the name-alone can't (decided by its
  شيخ). **يونس/الزهري flag CONFIRMED**: under شيخ=الزهري «يونس» → يونس بن يزيد الأيلي; «يونس عن الحسن» → يونس بن
  عبيد. This is the DISAMBIGUATION «شيخ-only relaxation» (line ~130) — deterministic, documentary, attacks the
  silent mis-ID class **better than tuning `canon._pick`'s heuristic threshold**.
- **Two resolvable clusters surfaced:** **S is dominated by «أبو إسحاق» (194+31 = 225)** — a kunya collision
  (سعد بن أبي وقاص · صحابي vs أبو إسحاق السبيعي · تابعي ثقة), which the relaxation resolves. **W (688) is a
  REVIEW QUEUE, not 688 errors** — it includes genuine متروك correctly graded (يحيى بن العلاء, طلحة بن عمرو,
  أبو هارون العبدي…); the real mis-IDs are a subset.
- **Graph-lag caveat:** this run's `build_graph` (step 7) unified names with the **old pre-#117** `rijal.jsonl`,
  so `canon._pick`'s company is stale → part of the A↑ is the lag, not just the discipline.
- **LLM cache was PARTIAL** (1652 cached, more suspicious chains remained) — I wrongly advised stopping the
  re-run to keep the baseline «pure»; the user (rightly) wants the LLM finished now (completes the cache →
  future runs fully cached/fast). Lesson: a small confound (LLM touches ~1–2% of chains) was not worth a
  re-run later. The user is re-running fully (lag-fix + LLM-complete).

**PLAN (sequenced, USER-CHOSEN — «one change at a time»):** **(1) clean lag-only baseline FIRST** — rerun the
tail only (`build_graph → build_rijal → audit_isnad`, or `update --no-llm`) so the graph rebuilds from the
**new clean** rijal and ONLY the lag changes → measure the lag's A-drop. **(2) Then implement the شيخ-only
relaxation** + tests. **(3) Re-measure.** Goal: turn «held» into «identified» where the شيخ decides — cut A
**without guessing** (keep W/S low).
**STATUS:** (1) **DONE** — the lag-fix re-run (graph rebuilt from the clean rijal **+ LLM completed**) gave
**W 716 · S 2921 · A 82,394** vs the prior **688/2918/82,678**: A moved only **−284 (−0.3%)** → **the lag was
NOT the lever**, confirming A is structural homonymy (the relaxation is the only lever). Baseline to beat: **A
≈ 82,394.** (2) **DONE — IMPLEMENTED on the branch** (`app/rijal/muhmal.py`): `build_map` also emits an
`"@<bare-ism>\t<شيخ>" → full` map (helper `_pick_unique`; شيخ gated by `_specific_shaykh` = ≥2 tokens OR a
single ال-nisba/laqab like الزهري — a bare common ism «محمد» is refused); `resolve` tries the exact
`(تلميذ,شيخ)` first, then the relaxation; the `@` sentinel can't collide with exact keys → **byte-compatible
with old `muhmal.json`**. 4 synthetic tests (يونس/الزهري resolves; homonymy held; generic-شيخ skipped; exact
precedence); **318 green**. **WAITING ON THE USER:** run `update.bat` (rebuilds `muhmal.json` *with* the
relaxation) → send the new **W/S/A** to measure the A-drop vs 82,394.

**★ AUDIT-DRIVEN FIX BATCH (2026-06-11, THIS SESSION cont.; on main, branch `claude/intelligent-bardeen-HAsrg`).**
The user ran the lag-fixed baseline (**W 716 · S 2921 · A 82,394**, 90,549 chains · 9,786 rijal) and pasted the
full «التدقيق». Investigating it against the real `rijal.jsonl`/`audit.json`/`muhmal.json` found + FIXED **5
systematic bugs**, each verified + tested + **ff-merged to main** (so `update.bat` applies them):
1. **شيخ-only relaxation** (`muhmal.py`) — the A lever (above). `[4f78406]`
2. **«ويقال» name-truncation** (`rijal_extract._NAME_CUT`/`_ALT_NASAB`) — تقريب's alternate nasab «… بن عبيد
   ويقال ابن علي … أبو إسحاق السبيعي» truncated the name, dropping kunya+nisba → أبو إسحاق السبيعي (a prolific
   تابعي) was unreachable, so a chain's «أبي إسحاق» fell to the lone صحابي with that kunya (سعد بن أبي وقاص) =
   the DOMINANT S pattern (≈229 in the 500-sample). Strip «(و)يقال ابن …»; السبيعي now keeps kunya+nisba. `[cdde14f]`
3. **«ابن أبي X» → descendant, not the kunya grandfather** (`index._is_nasab_ref`) — «ابن أبي مليكة» folded to
   the kunya «أبو مليكة» and grabbed the صحابي grandfather, not the تابعي عبد الله بن عبيد الله (ثقة فقيه).
   Teknonym suppressed for «ابن …» citations (≈180 S: ابن أبي مليكة/ذئب/ليلى/رواد → now held, not صحابي). `[f65af07]`
4. **ضبط pollution** (`rijal_extract._DABT`) — 726 names (7%) carried un-stripped vocalisation runs (بالتصغير،
   بمهملتين، بالمعجمة، بينهما…), breaking matching + dedup. Broadened _DABT (dual/plural + «بال» forms) → 96% of
   the leak removed on the real names. `[927bba6]`
5. **stale 3722 in the index** (`parse._drop_stale`) — parse SKIPS تهذيب الكمال 3722 but never deleted a
   `processed/3722.jsonl` left from before #103, so its ~8k tarjamas resurfaced as bogus «hadith» chains (the
   «[3722]» W/A rows with 60-narrator concatenated names). Now deleted on skip. `[80eb54d]`
**Expected:** S↓ a lot (#2+#3), A cut/cleaned (#1 relaxation + #4 dedup-unblock + #5 garbage gone), W↓ (#5 + #3
held). **WAITING ON THE USER:** **one `update.bat`** (rebuilds rijal+graph+muhmal+audit with ALL 5) → send the
new `rijal.jsonl`/`audit.json` + W/S/A vs **716/2921/82,394**; then I diff the recovered narrators (السبيعي &c.)
and measure. Smaller S patterns still open: «الأشعث» ال-mismatch · «خرشة» ضبط-doppione/grade · borderline مخضرمون
(محمود بن لبيد/الربيع، عنبسة — often legit صحابي عن صحابي).

**★ (2026-06-10, large session → #145). THE MATN-EXTRACTION ARC + the regex-vs-LLM split, decided
with a SAMPLE-DRIVEN method** (user extracts N real hadiths/book via `parse_book_file` → I run
`split_isnad_matn` vs the real text, categorise the cuts, fix the clean ones / flag the hard ones → main).
**Economics (measured on the samples): the regex does ~85-90% of matn and ~75% of narrators FREE &
deterministic on every update; the LLM repairs the hard ~10% — turning "LLM on all ~89k chains" into
"regex almost all + LLM only where it must" (~7-9× less LLM work). The 4 fixes below are the clean regex
wins; the rest is genuinely LLM territory.**
- **#142 narrators:** «يقول/تقول/فقال» → SOFT matn markers (were HARD → truncated the صحابي at «X يقول:
  سمعت Y» / «سألت X فقال: حدثني Y»). Found via **`--mode chains-diff` (#140)** — a diagnostic that runs the
  LLM on NON-suspicious chains and reports % narrator-alignment vs the regex. On 383 real chains: 70→71%,
  and the raw «49%» was mostly the **harmless Prophet-terminal CONVENTION** (regex keeps «النبي» as a node;
  the LLM stops at the صحابي). **So the regex base is SOUND — do NOT replace it with an LLM base** (~89k
  calls; corpus redundancy + identity-≠-boundary). The hard narrator truncations («عن X أنّ [صحابي] story»,
  «قُرِئ على», ح parallel routes) over-run into the matn if fixed naively → left to the LLM.
- **#143/#145 matn `split_isnad_matn` (clean regex, verified on real al-Mustadrak/أبو داود/الترمذي):**
  #143 — a quoted TITLE/reference in the commentary («… في "المسند الصحيح"», «في "مسند أنس"») was taken as
  the matn (losing the real unquoted one) or merged on → now the matn quote must be **SPEECH-introduced**
  («… قال/فقال: "…"»), and the extension stops at an editorial cue OR a **reference preposition** («في "…"»),
  all on diacritic-stripped text. #145 — the collection AUTHOR's note («قال أبو داود» in his Sunan, «قال
  أبو عيسى» in Tirmidhī) leaked into the matn (43/600 in أبو داود) → trimmed. **Tirmidhī's BARE verdict
  «حديث فلان حديث حسن صحيح» was attempted but REVERTED** (the regex over-trimmed real «حديث قصة»/«حديث
  منكر»); the **all-12-books pass** proved the remaining author-notes «قال مالك/أبو بكر/عبد الله/أبو عبد
  الرحمن» are **AMBIGUOUS** (also صحابة/narrators speaking IN the matn — «قال أبو بكر: ما كان لابن أبي
  قحافة…» is the Companion) → NOT regex-safe → LLM (it reads the context).
- **#144 matn detection:** `chain_is_suspicious` now also flags a botched matn (≤3 words while ≥8 words of
  body were dropped; back-references «نحوه/بمثله/فذكره» excepted) → the faithful LLM `--mode chains`
  re-segments it. ~10-14% of chains flagged on the samples — the LLM is pointed at exactly the hard tail.
- **build_rijal_llm hardening:** death-year override (**#135** — the LLM transcribes the literal Taqrib year;
  the regex's #122 century-from-طبقة is authoritative); per-book `--sample` (**#136** — it never left تقريب
  before); model-keyed cache (**#136** — enables A/B compare; switching models re-extracts); **dropped تهذيب
  الكمال from LLM rijal (#137)** — `iter_tarjamas` mis-segments its non-numbered dictionary → muqaddima
  garbage (al-Mizzī-as-narrator with ابن تيمية/الذهبي as students!); the regex `tahdhib_extract` already owns
  its network; chains scan ALL core collections (**#138**); **chains-only update by default, رجال opt-in
  `--llm-rijal` (#139)**; progress ticks + 180s timeout (**#141** — gemma4 cloud hit the 60s default on long
  chains). **Verdict (settled): LLM-rijal is MARGINAL** — تقريب/الكاشف carry no شيوخ/تلاميذ network (the LLM
  can't extract what isn't there) and where the network IS (تهذيب 3722, الجرح 2170) the regex extractors get
  it; the LLM's unique value is `--mode chains` (matn/isnād re-segmentation).

**Method gotchas (reusable):** the LLM-cache reconstruction is **CONFOUNDED for the matn** (it converts «» →
" , and `split_isnad_matn` is quote-driven), so the matn MUST be diagnosed on real book text, not the cache
(narrators are fine — they're before the quotes). The container **can't pull the 15-30MB books** (network
allowlist blocks Drive/turath; the Google_Drive MCP would dump ~20MB base64 into context) — the user runs
the slice command and uploads the small (~KB-MB) result; small Drive files ARE fetchable via the
`Google_Drive` MCP (`search_files` by title, `download_file_content` by id).

**Waiting on the user:** run `update.bat` with the LLM enabled (`LLM_DEFAULT_ENGINE=local` or `--llm`) →
the regex applies #142–#145 corpus-wide AND the LLM repairs the flagged ~10% → send the new W/S/A and
eyeball the matns.

**★ (2026-06-09, large session → #129).** Two arcs on main; user to run `update.bat` (and,
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

**★ FOLLOW-UP (2026-06-10): dedicated extraction model wired into update («mettilo nell'update»).**
Added `llm_extract_model` (default **`ollama/gemma4:31b-cloud`** — the only free+fast Ollama-Cloud model;
minimax/nemotron are free but reasoning→~30s, too slow for a 16k-call batch; kimi/glm need a paid sub).
`build_rijal_llm` gained `--model` (precedence `--model` > `--engine` > `llm_extract_model`); a **bare**
invocation now uses the extract model with **zero `.env` juggling** (`api_base`=local Ollama for any
`ollama/…`). `update.py` passes `--model settings.llm_extract_model`, so update.bat always extracts with
gemma4:31b-cloud regardless of what `llm_local/remote_model` are set to. User still needs
`LLM_DEFAULT_ENGINE=local` (or `--llm`) to *enable* the LLM step. NB the user hit `ModuleNotFoundError:
scripts` by running from `…\build\data\` — must run from the **repo root** (`cd ..`).

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
