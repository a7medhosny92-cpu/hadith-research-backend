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
1. **Order-aware name matching (RIJ).** Add a sequence check to `RijalIndex.lookup` so
   «يزيد بن جابر» ≠ «جابر بن يزيد» (token-set matching loses order today). *Effort: low.*
   *Validate:* the rijal gold set (no new false matches; same true matches).
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
8. **Rich rijal from the verbose corpus.** From تهذيب الكمال / الجرح والتعديل extract the
   *quoted critic statements* per narrator (قال أحمد… / قال ابن معين…) — like the أحكام but
   for الرجال — giving a detailed, sourced جرح وتعديل page per narrator. *Effort: high.*
   *Validate:* sample narrators against the printed entries.

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
