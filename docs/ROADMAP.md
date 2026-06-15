# Improvement Roadmap — Hadith Research Backend

The audit (`docs/AUDIT.md`) fixed correctness. This roadmap is the **forward** plan: the
improvements named in the in-app «البنية» page, turned into a staged, evidence-driven
programme. Same discipline as the audit — **measure, then change**; each item ships as a
focused PR with tests, behind green CI.

## Guiding principles
- **Don't regress the guarantee:** retrieve & cite, never invent; transmitted data stays
  authoritative, analytical data stays reviewable.
- **Measure everything:** no model/heuristic change lands without a number moving on a
  held-out set (Phase 0 builds those sets).
- **Cheap, high-value first:** order by *value × feasibility*, not by glamour.
- **Stay local-first:** it must keep running on the user's CPU-only machine; heavy steps
  are opt-in and one-off.

---

## Track A — Narrator identity (تمييز المهمل) — the main recent programme
The bulk of audit flags are **A («مشترك»)**: a name matching several men. This track resolves the
identity *from the chain*, never by guessing. See `docs/ARCHITECTURE.md §11` for the full design.

**Done (measured on the user's real corpus, 84,783 chains · rijal ≈20k).**
- Order-aware matching (`_order_ok`), coverage drop (`_prefer_non_coverage`), the «ابن X» eponym guard.
- **Corpus redundancy** (`muhmal.py`) + the شيخ-only relaxation.
- **Company** (`canon._pick`) enriched by تهذيب/الجرح/الثقات (`_NETWORK_SOURCES`).
- **The joint resolver** — تمييز المهمل بالشيخ والتلميذ (`resolve.py` + `documented_students` →
  `documented_network.json`, wired into `analyze_isnad`): anchored, directional, positive-evidence,
  the classical method grounded in the curated books. **A −15 % on its own.**
- **The prominence prior** (`_prefer_prominent`, gated by `apply_prominence`).
- **Coverage** (الإصابة 9767, الثقات 96165, add-only) + **named-critic verdicts** (`appraisals.py`).
- **Node hygiene** — the waw-dual co-narrator split + `scripts.audit_nodes` (the parsing-bug detector).
- **Net result: A 85,184 → 56,182 (−34 %) with S and W flat-to-better** — a third of the ambiguity
  resolved at no cost in wrong verdicts.

**Open levers (the residual A, ordered by value × feasibility).**
- **A.1 Name-granularity shadows.** A bare/truncated entry («محمد بن جعفر») shadows the famous man
  (غندر «محمد بن جعفر الهذلي»), so the documented network can't match the full key → held. Cure:
  upstream name normalisation / merge the bare shadow into the fuller entry (extends `dedup.py`).
- **A.2 Better anchoring.** Seed the joint resolver with more confident anchors — the terminal صحابي
  by *position* (not only unique-name) and the deterministic `muhmal` resolutions — so propagation
  reaches more mid-chain links.
- **A.3 More network coverage.** Each new prose رجال source (لسان الميزان, الطبقات, أسد الغابة…) adds
  documented شيوخ/تلاميذ → the resolver reaches more men outside the current تهذيب/الجرح/الثقات core.
- **A.4 Shuhra-by-ancestor.** A man known by a *distant* ancestor's name («ابن جريج» = عبد الملك بن
  عبد العزيز بن جريج) isn't reached by the leading-run rule — a targeted matching enhancement.
- **A.5 The honest floor (②b).** Two comparably-prolific men with shared company (سفيان عيينة/الثوري
  flanked by their common teachers) — *correctly* held; not chased. The goal is **not A = 0**.

---

## Phase 0 — Foundations (evaluation & free training data)
Nothing else is trustworthy without these. Small, fast, no models.

- **0.1 Gold sets (hand-checked):**
  - *parsing* — ~200 hadith with إسناد/متن boundary + grade annotated.
  - *retrieval* — ~100 query→correct-hadith pairs (incl. paraphrases).
  - *isnad* — ~50 chains with a known scholarly verdict.
  - *rijal* — ~100 narrator names (as written in chains) → the intended person.
- **0.2 Free training pairs from التخريج:** the صيغ of one report (already grouped per
  Companion) are *paraphrase positives*; different reports are negatives. This gives
  thousands of labelled pairs **for free** — the fuel for Phase 2.
- **0.3 Metrics harness:** `scripts/eval.py` printing parsing-F1, retrieval recall@k/MRR,
  isnad-verdict agreement, rijal-resolution accuracy — run in CI on the gold sets.

*Deliverable:* `data/gold/*.jsonl` (tiny, committed) + `scripts/eval.py`. **Effort: low.**

## Phase 1 — Quick wins (high value, data already in hand)
1. **Order-aware name matching (RIJ).** *Status: **DONE** (`_order_ok` + leading-run containment).*
   «يزيد بن جابر» ≠ «جابر بن يزيد»; shared tokens must appear in the same relative order.
2. **«Double opinion» rijal (الرأي الثاني).** We already extract Ibn Ḥajar (تقريب) **and**
   al-Dhahabī (الكاشف). Instead of merging to one verdict, **keep both** and, when they
   differ, show «ثقة عند ابن حجر · صدوق عند الذهبي» in the narrator & isnad cards. Needs a
   per-narrator *list* of (source, verdict) rather than a single grade; the isnad verdict
   takes the *weakest among the agreed*, and flags divergence. *Effort: medium.*
   *Validate:* spot-check known mukhtalaf-fīhi narrators.
3. **علل extraction (الحكم بالعلّة).** Treat the علل literature (cat-9: علل الدارقطني, علل
   ابن أبي حاتم — already in scope) like the أحكام: extract *stated* defects for a report
   (وقفه فلان، أعلّه فلان، الصواب إرساله…) and surface them on the hadith. This is the
   *documented* علّة — extractive, feasible now. *Effort: medium.*
   *Validate:* against a handful of famously-معلول hadith.

## Phase 2 — Domain models (use the free data from Phase 0)
4. **Fine-tune the embedding model.** Contrastive fine-tuning of the Arabic embedder on
   the التخريج pairs (0.2): the same report's صيغ pulled together, different reports pushed
   apart. Matryoshka keeps the 768-dim drop-in. *Effort: medium (a few GPU-hours, one-off;
   the build step stays inference-only).* *Validate:* retrieval recall@k up on the gold set
   vs the stock model; ship only if it wins.
5. **Reranker (cross-encoder).** Re-score only the top-k retrieved candidates for relevance
   to the query (not the whole corpus, so cost is bounded). *Effort: medium.* *Validate:*
   MRR/recall on the retrieval gold set; gate behind a setting (RAM).

## Phase 3 — Deeper extraction & criticism
6. **Finer إسناد/متن & grade parsing.** Move from pure heuristics to weak-supervision: use
   today's heuristics as noisy labels, hand-correct the gold set, train a lightweight Arabic
   token-classifier (إسناد / متن / حكم). Fall back to heuristics when confidence is low.
   *Effort: high.* *Validate:* parsing-F1 on the gold set beats the heuristic baseline.
7. **Structural علّة/شذوذ signals.** Beyond *stated* علل (item 3), *detect* candidates by
   comparing the طرق already gathered by التخريج: رفع vs وقف / وصل vs إرسال across routes →
   possible علّة; a lone ثقة against more/أوثق narrators → possible شذوذ/تفرّد. Always framed
   as **a hint to investigate**, never a verdict. *Effort: high.* *Validate:* precision on
   known cases (favour few, correct flags over many noisy ones).
8. **Rich rijal from the verbose corpus.** *Status: **PARTLY DONE** — `appraisals.py` extracts the
   named «أقوال الأئمة» (قال ابن معين… / ذكره ابن حبان…) from الجرح/تهذيب/الثقات and shows them on the
   «راوٍ» card.* Remaining: widen the curated نقّاد list and add more prose sources. *Effort: high.*

## Phase 4 — Scale (only if it goes multi-user / web)
9. **Postgres + pgvector backend.** Implement the production backend the scaffold already
   anticipates (replacing the sqlite dev indexes) for concurrency and larger-than-RAM
   vectors. *Effort: medium.* **Priority: low while it stays a single-user local app.**

---

## Priority summary
| # | Improvement | Value | Effort | Phase |
|---|---|---|---|---|
| 1 | Order-aware name matching | med | **low** | 1 |
| 2 | Double-opinion rijal | **high** | med | 1 |
| 3 | علل extraction (stated) | **high** | med | 1 |
| 4 | Fine-tuned embedding (التخريج pairs) | **high** | med | 2 |
| 5 | Reranker | med | med | 2 |
| 6 | Finer إسناد/متن/grade parsing | **high** | high | 3 |
| 7 | Structural علّة/شذوذ signals | **high** | high | 3 |
| 8 | Rich rijal (verbose corpus) | med | high | 3 |
| 9 | Postgres + pgvector | low* | med | 4 |

\* low *while local/single-user*; high if it becomes a web service.

## Cross-cutting
- Every model added is **opt-in** and respects the RAM budget (semantic search already
  showed the constraint); the extractive/lexical baseline always remains.
- The in-app «البنية» and «المنهجية» pages are updated whenever any of these lands.
- The التخريج pairs (0.2) are the keystone: they unlock both the embedding fine-tune (4)
  and the structural علّة/شذوذ work (7) at no labelling cost.
