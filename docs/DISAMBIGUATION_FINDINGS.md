# Narrator disambiguation — measurement findings (remote, Ṣaḥīḥayn subset)

A durable record of a remote measurement session: building the pipeline on a Bukhārī+Muslim
subset and quantifying how far the «held» (مشترك) narrators can be resolved **with certainty**,
and what blocks it. Numbers are **indicative** (subset, not the full corpus) and were produced on
an ephemeral container; the **code** is the source of truth, this file is the **reasoning record**.

> TL;DR — The classical triangle (**name + company + ṭabaqa**) is the right model and is what we
> built. But the dominant error is **not** the honestly-held ambiguous cases — it is a class of
> **silent confident MIS-identifications** made by `canon._pick`'s *diffuse token-overlap* (e.g.
> «يونس عن الزهري» → confidently `يونس بن عبيد`, wrong, `ambiguous=False`, unflagged; **more context
> makes it worse**). The fix is to disambiguate by the **specific neighbour's documented roster**
> (شيخ→students / تلميذ→teachers) as a **hard constraint with hold-by-default** — which is both the
> certainty discipline and the «company» method.

## وصف المشكلة بالعربية — the problem, in Arabic

**أولاً: أصل المشكلة — تمييز الراوي المهمَل والمشترك في الإسناد.**
كثيرٌ من الأسانيد يُذكَر فيها الراوي باسمٍ **مجرَّدٍ ناقصٍ** لا يكفي لتعيينه؛ كأن يقول المحدِّث:
«حدثنا محمد» أو «عن يونس» أو «عن عبد الله»، وفي طبقة شيوخه أكثرُ من رجلٍ بهذا الاسم. هذا هو **الراوي
المهمَل**، وهو من باب **المتفق والمفترق** في علوم الحديث. والسؤال الجوهري: **أيُّ «يونس» هو؟** فإن لم
نُعيِّنه لم نعرف حاله، ولم يصحَّ الحكم على الإسناد.

**ثانياً: لماذا هي مشكلةٌ خطيرة.** الحكم على الإسناد (صحيح / حسن / ضعيف) مبنيٌّ على **حال كلِّ راوٍ**
(عدالته وضبطه) و**اتصال السند**. فإذا أخطأنا في تعيين راوٍ مهمل نسبنا إليه جرحاً أو توثيقاً ليس له
(نأخذ درجة **رجلٍ آخر** يشاركه الاسم)، فيختلّ الحكم: نصحِّح ما حقُّه التضعيف، أو نضعِّف ما هو صحيح.
وهذا أخطر من الخطأ الظاهر، لأنه **خطأٌ خفيٌّ صامت**.

**ثالثاً: القرائن الصحيحة للتعيين** هي قرائن الإسناد نفسه، على منهج المحدِّثين: **«يُميَّز المهمَل
بشيخه وتلميذه وطبقته»**:
- **الشيخ والتلميذ (الصُّحبة):** عمَّن روى ومَن روى عنه؟ فلكلِّ راوٍ شيوخٌ وتلاميذُ معروفون.
- **الطبقة (الزمن):** الشيخُ يتقدَّم تلميذَه؛ فموضعُ الراوي في السند يحدِّد جيله، ويُخرِج مَن كان من
  طبقةٍ أخرى.
- **اسمه المكتمل** إن ورد مُسمًّى في موضعٍ آخر (تمييز المهمل بالمسمَّى، من تَكرار النصوص).
ولا يصحُّ الاعتماد على **الدرجة** في التمييز: الجرح والتعديل يُخبر عن **قيمة** الرجل لا عن **عَينه**.

**رابعاً: الخلل الدقيق الذي اكتشفناه (لُبُّ المشكلة).** نظامنا، حين يميِّز بـ«الصُّحبة»، يعتمد على
**تشابهٍ عامٍّ مبهمٍ** بين الأسماء المحيطة (تقاطُع كلماتٍ)، لا على **العلاقة المعيَّنة** (هل هذا
المرشَّح تلميذٌ لذلك الشيخ **بعينه**؟). ومثاله الجليّ: في «… عن **يونس** عن **الزهري** …»، فـ«يونس»
المرويُّ عن الزهري هو **يونس بن يزيد الأيلي**؛ لكنّ النظام عيَّنه **بثقةٍ** على أنه **يونس بن عبيد**
(بصريٌّ يروي عن الحسن، لا عن الزهري) — **تعيينٌ واثقٌ خاطئ بلا تنبيه**. والأعجب: **كلَّما زاد سياقُ
السند زاد الخطأ**، لأن التشابه العام يُرجِّح بالمصادفة رجلاً غيرَ مقصود؛ والرجلُ الصحيح (الأيلي) كان
حاضراً بين المرشَّحين لكنه خَسِر أمام «الضجيج».

**خامساً: ما نطلبه — اليقين لا الترجيح الظنّي.** نُعيِّن الراوي **فقط** إذا دلّت عليه قرينةٌ قاطعة:
**نصُّ المصدر** (تهذيب الكمال «روى عن فلان»، أو الغسّاني في «تقييد المهمل» على رجال الصحيحين)، أو
**الإسقاط** (لم يبقَ بعد تطبيق القرائن إلا رجلٌ واحدٌ ممكن)؛ وما عدا ذلك **نتوقّف فيه** (نعرض
المرشَّحين ولا نجزم). والإصلاح الجوهري: أن يكون التمييز بـ**صُحبة الجار المعيَّن** (شيخِه أو تلميذِه
بعينه) **قيداً صارماً**، لا تشابهاً عامًّا.

## The audit flags «أعلام التدقيق» (P / S / W / A)

`scripts/audit_isnad.py` scans every chain and raises four flags into `data/audit.json` (the
«التدقيق» review tab). Each is a **candidate error for a human to verify**, never a verdict:

| flag | label (Arabic) | what it means | when it fires |
|---|---|---|---|
| **P** | الحكم على النبيّ ﷺ كراوٍ | the Prophet ﷺ was matched/graded as if he were a narrator — must **never** happen | whenever a Prophet node carries a rijal grade |
| **S** | «صحابي» في غير آخر السند | a **Companion** graded **mid-chain** — a صحابي belongs in the last 1–2 links, so a mid-chain match is almost always a **homonym mismatch** | only when the match is *certain* |
| **W** | اسمٌ كاملٌ حُكم له بالترك/الكذب | a **fully-named** narrator (≥3 tokens) graded **متروك/متهم/كذاب/وضاع** — usually a homonym mismatch condemning the wrong man | only when the match is *certain* |
| **A** | مطابقةٌ مشتركة (مُلتبسة) | the bare name matches **more than one** man (**مشترك**) — the core ambiguity this study is about | on **any** ambiguous match |

Gate: **S and W fire only when the identification is "certain"** (the match is unambiguous, or its
tied candidates agree on the grade, `grade_agreed`); an ambiguous-and-grade-disagreeing case is
routed to **A** («مشترك»), never to a confident صحابي/متروك flag.

> **Why these flags miss the dangerous case.** The silent confident mis-identification above
> («يونس عن الزهري» → `يونس بن عبيد`) is **not** P (not the Prophet), **not** A (`ambiguous=False`),
> and **not** W (يونس بن عبيد is ثقة, not متروك). So **none** of P/S/W/A catches it — which is exactly
> why this class of error is the most dangerous, and why the `canon._pick` fix matters most.

## Setup (what was run remotely)
- Books (uploaded): **1284** Bukhārī, **1727** Muslim (chains); **8609** تقريب + **2171** الكاشف
  (grades); **3722** تهذيب الكمال (network). No شروح, no semantic (irrelevant to A).
- Pipeline: parse → index → build_rijal → build_graph → build_rijal → audit (convergent order to
  avoid the one-iteration graph/rijal lag).
- Sizes: **13,565** hadith parsed (**13,538** with isnād); rijal **9,634** entries (+92 seed);
  graph **6,482** nodes / **17,458** links; muhmal subset map **1,403** contexts.
- Caveat: subset ≈ 15% of the user's full corpus; chains are عالية (short) → compressed depth scale.

## Audit baseline (subset, dedup #109 + muhmal #110 active)
**P 0 · W 24 · S 738 · A 6241.**

### The A-count is a misleading metric
A fires on **any** ambiguous match, even when the tied candidates **agree on the grade**. Decomposing
the 6241:
- **1160** are `grade_agreed` — the man is identified and gradable, just multi-matched (often an
  un-collapsed same-man duplicate). **Not real problems.**
- **5081** are genuinely **held** (يُتوقَّف — candidates disagree on grade). **This is the real target.**

2×2 on A (dedup × muhmal): baseline (both off) 5883 → (both on) 6241. **Neither lever lowers A.**
muhmal *raises* A (+~350) by surfacing identified-but-still-ambiguous narrators as honest holds
(consistent with «A rose as confidently-wrong became honest held»); dedup is ≈0 on the subset
(its value is high-frequency duplicates on the **full** corpus).

## How far the signals resolve the 5081 «held» (each measured)
| signal | coverage | death-year-free? | resolved (held) |
|---|---|---|---|
| **death-year** (generational window) | 52% have distinct deaths | ✗ | ~917 *(noisy; some spurious)* |
| **ṭabaqa from chain depth** (the corpus-internal idea) | 1057 narrators get a ṭabaqa | ✓ | 206–406 *(48–131 new beyond death-year)* |
| **explicit طبقة in تقريب** (Ibn Ḥajar's 12 layers) | **88.4%** (7806/8827) | ✓ | the coverage unlock |
| **company** (شيوخ+تلاميذ rosters, both sides) | — | ✓ | **1580** |
| **company + ṭabaqa (union)** | — | ✓ | **2698 = 53%** of held; **1216** without any death-year |

The classical rule is literally **«يُميَّز المهمل بشيخه وتلميذه وطبقته»** — distinguish by teacher,
student, generation. The three signals = that triangle.

## The certainty findings (the important, humbling part)
1. **Heuristic «picks» disagree.** Where company *and* ṭabaqa both fire (709 cases), they pick the
   **same man only 72 times (~10%)**. Soft «closest/highest» scoring is a **noisy guess**, not
   certainty. The «53% resolved» was each signal guessing independently; they do **not** concur.
2. **Documentary resolution is clean but tiny here.** Using تهذيب's روى عن/عنه as the sole judge
   (a candidate is confirmed iff تهذيب lists the actual شيخ among his teachers / تلميذ among his
   students): of 5081 held, only **460** have any candidate with a تهذيب roster, and only **52** are
   uniquely confirmed. On the full corpus + complete تهذيب this grows, but on the subset it is small.
3. **THE KEY BUG — silent confident mis-identification (`canon._pick`).** For «… عن يونس عن الزهري …»:
   - the right man **يونس بن يزيد الأيلي IS among the 26 candidates** (not a candidate-generation bug);
   - `canon.canonical("يونس", clean-context)` → keeps **«يونس»** (held — correct);
   - but with the **full noisy chain context**, `_pick` finds a **spurious unique winner**:
     **`يونس بن عبيد`** (a Baṣran who narrates from الحسن, **not** from الزهري), with
     **`ambiguous=False`** → confident and **wrong**, and **unflagged** (يونس بن عبيد is ثقة → no W;
     not ambiguous → no A).
   - **Paradox: more context → worse**, because `_pick` scores by *diffuse token overlap* of company,
     and a wrong candidate's company accidentally overlaps more. These **silent mis-identifications**
     are more dangerous than honest holds, and the whole W/S/A audit misses them.
4. Full-corpus muhmal map (user-uploaded, **11,827** contexts vs the subset's 1,403) swapped in →
   audit A **6241 → 6177 (−64)**: modest, confirming the bottleneck is **not** muhmal coverage but the
   rijal-DB / `_pick` quality downstream. (The full map *does* contain `(…, الزهري) → يونس بن يزيد الأيلي`,
   but the exact `(تلميذ, شيخ)` pair of the failing chain wasn't mapped — the **شيخ-only relaxation**
   would catch it.)

## Conclusion & the fix
- **Certainty must be documentary or by hard elimination, never heuristic scoring.** Assert an
  identity only when a source confirms it (تهذيب روى عن/عنه, the corpus naming him in full = muhmal,
  or al-Ghassānī) **or** when hard constraints leave exactly one possible man; otherwise **hold**.
- **The single highest-leverage change: rewrite `app/rijal/canon.py::_pick`.** Replace diffuse
  token-overlap with **specific-neighbour evidence**: among the candidates, keep those documented to
  narrate **from the actual شيخ** and/or **to the actual تلميذ** (graph edge `link_weight`, and/or
  تهذيب roster). Pick **only** a unique survivor; else keep the surface form (held). This:
  (a) eliminates the silent mis-identifications (يونس no longer becomes يونس بن عبيد);
  (b) enforces certainty-by-elimination; (c) **is** the user's «look at the maestro and his students»
  method, both sides.
- **The real bottleneck is data, not method:** complete the candidate sets and the تهذيب/طبقة
  extraction, and re-measure on the **full corpus** where muhmal-explicit (the most certain signal)
  scales ~9×. Recover **al-Ghassānī's «تقييد المهمل»** (hand-resolved muhmal of the **Ṣaḥīḥayn** — our
  exact subset) as the gold standard to measure **precision**, not coverage.

## The literature (the science behind this)
- Umbrella (where the rule lives): **مقدمة ابن الصلاح**; **فتح المغيث — السخاوي** (most detailed on
  المهمل and distinguishing by شيخ/تلميذ); **تدريب الراوي — السيوطي**; **نزهة النظر — ابن حجر**.
- Same name → different men: **«المتفق والمفترق» — الخطيب البغدادي**.
- Dedicated to the muhmal: **«تقييد المهمل وتمييز المشكل» — أبو علي الغسّاني الجيّاني** (on the Ṣaḥīḥayn);
  **«المكمل في بيان المهمل» — الخطيب**.
- Generations: **الطبقات الكبرى — ابن سعد**; the 12 طبقات in **تقريب التهذيب**.
- Network + grades: **تهذيب الكمال — المزي** (روى عن/عنه); **الجرح والتعديل — ابن أبي حاتم**.
- Modern computational peers (to evaluate, not copy): **Itqan** (open narrator DB + disambiguation
  rules), **AR-Sanad 280K** (narrator-disambiguation dataset), **SPADE on Bukhārī** (narrator-network
  mining).

## Live cases (found by inspecting the running app)
- **أبو ذر الغفاري not recognised as صحابي.** He is cited by his **kunya** «أبي ذر», which is **مشترك**:
  it matches جندب بن جنادة الغفاري (صحابي — the Companion), عمر بن ذر الكوفي (ثقة), منير الأردني (ضعيف),
  and a **false** candidate خالد بن وهبان whose kunya «أبي ذر» was wrongly extracted from his name
  «… ابن خالة أبي ذر» («son of Abū Dharr's aunt»). The candidates disagree on grade → held (or, on the
  full DB, a confident wrong ثقة pick). **Fix:** resolve by **position/طبقة** (the last link is the
  Companion) + company, and fix the kunya extraction («خالة أبي ذر» is not a kunya). *(open)*
- **«أنس بن مالك» merged with «مالك بن أنس» in the graph.** The graph node key was order-independent
  (`sorted(name_tokens)`), so the Companion (al-Zuhrī's **teacher**) and Imam Mālik (his **student**)
  — anagrams in token space — collapsed into one node, and the Imam's student-edge surfaced the
  Companion among al-Zuhrī's تلاميذ. **FIXED:** `app/rijal/graph.py::node_key` now preserves token
  order; verified the two resolve to distinct nodes and land in the correct شيوخ/تلاميذ lists. This
  also de-noises the company signal that `canon._pick` consumes.

## Fixed — 2026-06-09 session (#117 / #118 / #119)
All landed on `main` with synthetic regression tests (291 green); the A-impact is to be **measured on
the user's machine after `update.bat`** — the container has only a sample rijal and full scans hit exit 144.

- **Terminal-صحابي promotion gated on `reaches_prophet`** (`isnad.py`, **#117**) — refines the earlier
  «ultimo anello = صحابي» rule, which over-fired on **موقوف/مقطوع** chains: a تابعي giving his own مقطوع
  (الأسود النخعي · ثقة) was force-promoted to the homonym الأسود بن سريع · صحابي — a *confident wrong*
  identification, the very class we fight. Now the promotion fires **only when the chain actually ends
  at the Prophet ﷺ**; a genuine Companion at a non-مرفوع terminal (أبو ذر) is still kept by his natural
  lookup (`lookup("أبي ذر") → جندب الغفاري · صحابي`, verified), so nothing is lost. الأسود in his own
  مقطوع is now honestly **held** (ambiguous), never a confident صحابي.
- **Chain/matn boundaries tightened** (`isnad.py`, **#117**): (a) a back-reference «بهذا الإسناد /
  بإسناده / بسنده» ends the chain (was: «الإسناد» became a bogus narrator node); (b) a hadith-number
  cross-reference «م - ٢٣٤٥» and a lone ramz letter (خ م د ت س ق …) are dropped; (c) action verbs that
  open a narrated scene (يخطب/يصلّي/يحدّث/يذكر…) are a **soft** matn boundary — they end the chain
  *unless* a transmission verb follows, so «سمعته يحدّث عن أبيه» keeps the link while «كان يخطب الناس» stops.
- **تحويل (ح) is a route seam** (`isnad.py`, **#117**) — the narrator before a ح and the one after it
  are on different routes, so they are no longer read as a تلميذ→شيخ link (`continuity`) nor used as
  each other's disambiguation company (`canon`/`muhmal`). The seam was a silent false link.
- **Death-year ≠ age** (`rijal_extract.py::_death_year`, **#118**) — the parser took the first digit run
  after مات/توفي anywhere, so «مات وهو ابن ٨٧ سنة» (died **aged** 87) became death-year 87, and a leading
  age «سنة» («… سنة سنة خمسين ومائة») hid the real year 150. Now the year is anchored on the «سنة»
  *followed* by a number, skipping an age «سنة»; the no-«سنة» al-Kashif form falls back to the first
  non-age digit run. A wrong death year had been causing **false `dedup.same_man` merges** (death ±20).
- **Prophet ﷺ is never a *student*** (`graph.py::add_chain`, **#119**) — a mid-chain-parse «Prophet
  narrates from X» edge is dropped, keeping the real «X → Prophet» edge. Removes impossible edges that
  polluted the company data `canon._pick` consumes.

## Fixed — earlier arc (#111–#114, Companion audit)
- **Graph node-key order** (`graph.py::node_key`) — «أنس بن مالك» ≠ «مالك بن أنس». *(merged #111)*
- **Kunya from a relative** (`rijal_extract.py::_own_kunya`) — «خالد بن وهبان ابن خالة أبي ذر», «… أخو أبي بكر»,
  «… ختن أبي توبة», «محمد بن أبي بكر» no longer take a relative's / the father's kunya.
- **`canon._pick` silent mis-identification** — two parts: (1) `isnad.py` disambiguates by the
  **immediate neighbours** (the specific شيخ/تلميذ), not the whole chain; (2) `canon.py` no longer lets a
  narrow lookup group override a **held** full-set decision. Result: «يونس عن الزهري» now **holds**
  (`ambiguous=True`) instead of confidently يونس بن عبيد.
- **«ultimo anello = صحابي»** (`isnad.py`, تمييز بالطبقة) — a name at the terminal (Companion) position
  matching a صحابي is graded صحابي. Result: «… عن أبي ذر» → **جندب بن جنادة الغفاري · صحابي** (was ثقة).
- **`graph.resolve()` fallback is now order-aware** — it prefers the query as a **leading run** of the
  node's ordered key, falling back to a token-subset only for nisba-only queries. `resolve('أنس')` →
  **أنس بن مالك** (the Companion), not مالك بن أنس; «الزهري» → «محمد بن مسلم الزهري» still resolves.
- **«نسبه»/«رماه» no longer force كذاب** (`rijal_extract.py` `_FALLBACK`) — the bare verbs are benign
  («نسبه إلى تلقين», «رماه بالقدر»); only the accusation («إلى الكذب/بالوضع») grades كذاب. «الحسن بن
  مدرك … لا بأس به» now **صدوق**, while «… نسبه إلى الكذب» stays **كذاب**.
- **Deep Companion audit** (تمييز الصحابة) — across 13,538 chains, **8110** terminal Companions
  recognised, **0** mis-identified. It surfaced three more fixes:
  - **«صحابي» mid-chain → prefer the non-صحابي** (`isnad.py`, symmetric to the terminal rule): «جرير»
    deep → جرير بن عبد الحميد · ثقة (not جرير البجلي · صحابي); same for ابن وهب, ثابت, أبي إسحاق. Applied
    only **deep (≤ terminal−2)** so the **penultimate** link keeps **صحابي عن صحابي** (a younger Companion
    narrating from an older one: «أنس عن أبي بكر», «ابن عباس عن عمر» — else أنس wrongly became أنس بن سيرين).
  - **Accusative tanwin alif** (`normalize.py`): «جابرًا»/«مجاهدًا» now normalise to «جابر»/«مجاهد» and
    resolve (were `None`) — the alif is dropped before the harakāt are stripped.
  - **Kinship particles refused** (`index.py` `_NON_IDENTIFYING`): «أبيه»/«جده»/«أمه» no longer match an
    entry that merely mentions them («جعفر بن أبي ثور واسم أبيه عكرمة»).
- 279 tests green, + regression tests.

### Open (from the Companion audit)
- **[MED] Female / kunya Companions missing** — «أم عطية» (الأنصارية, صحابية) → `None`; the كنى/النساء
  section escapes extraction.
- **[MED] «و» co-narrators** not parsed («محمد بن المثنى وابن بشار»; «و» itself taken as a narrator) —
  still open (a co-narrator split turns the chain into a small DAG; deferred deliberately).
  *(The «بهذا الإسناد» back-reference half is FIXED in #117 — it now ends the chain.)*
- **[LOW] «أبيه»/«جده» not yet *resolved*** to the real ancestor at verdict time (currently only refused;
  the graph's kinship anchoring runs at build time only).

## Open bugs (found by a bug-hunt pass — to fix next)
- **[HIGH] Bare theophoric ism mis-identified** (`rijal_extract.py`, `index.py`): «عبد الرحمن»/«عبد العزيز»
  fold to 2 tokens → escape the generic-name/single-token drops → `lookup('عبد الرحمن')` resolves
  **confidently** to a مجهول/ثقة. Treat «عبد/عبيد + الله/الرحمن/العزيز/الملك/…» as non-identifying when it
  is the whole name.
- **[MOSTLY FIXED #118] Death-year vs age / hundreds** (`rijal_extract.py` `_death_year`): the age
  «مات وهو ابن ٨٧ سنة» was read as year 87, and a leading age «سنة» hid the real year. Now anchored on
  «سنة»+number (spelled hundreds parse correctly: «ست وثلاثين ومائتين» → 236). *Residual:* a source that
  genuinely **omits** the century yields no year (safe) rather than a wrong one — inferring the century
  from طبقة is still a possible future refinement.
- **[MEDIUM] body-fallback grade takes the LAST verdict** (`rijal_extract.py` `_extract_grade`): «… صدوق …
  وابنه ضعيف» → grade ضعيف (the son's). Prefer the first verdict / stop at «وابنه/وأخوه/وعنه».
- **[LATENT] `graph.disambiguate` sorted keys** (`graph.py` ~170) — same anagram family, safe only while
  `_AMBIGUOUS` keys stay single-token.

## Next steps
1. **Measure first.** The user runs `update.bat` (applies #117/#118/#119, rebuilds rijal + graph,
   regenerates the audit) and reports the new **W/S/A** from «التدقيق». This both shows the impact of
   this session's fixes AND is the prerequisite for step 2 — `canon._pick` cannot be tuned in the
   container (sample rijal only; full scans exit 144).
2. **Then tune `canon._pick`** (precision-first): a unique winner on a *thin, single-token* overlap —
   especially a generic nisba («الكوفي», «البصري») — should HOLD, not pick. Decide the threshold (e.g.
   require ≥2 distinctive shared tokens, or exclude generic nisbas) from the measured A, not blindly:
   too aggressive tanks the resolution rate. The #119 graph guard already de-noises the input company.
3. Acquire **al-Ghassānī** as the precision gold; complete تهذيب/طبقة extraction; co-narrator «و» split.
