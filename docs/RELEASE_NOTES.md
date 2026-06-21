[العربية](https://github.com/a7medhosny92-cpu/hadith-research-backend/blob/main/docs/RELEASE_NOTES.ar.md) · 🌐 **English**

# v0.1.0 — بحث وتحقيق الحديث · First public release

**An AI‑powered, local‑first system for searching the Prophetic traditions, verifying the chains of narration (isnād), grading the narrators, and detecting hidden defects (ʿilal) — entirely in Classical Arabic, fully offline.**

This is the first public release. It documents, in detail, the work built so far.

---

## Why this project exists

In the science of ḥadīth, a wrong attribution is a serious error. So the system is built on one discipline that runs through every layer: **«لا نختلق» — it never fabricates.** It retrieves a tradition from real, edited sources, cites it precisely (book · volume · page · number · grade), reasons over its chain narrator‑by‑narrator, and then states clearly *what is known* versus *what must be held*. Every datum traces back to a verifiable source text — and when the evidence is inconclusive, the system holds rather than guesses.

---

## Highlights

- 🧬 **A narrator‑identification engine** that resolves an ambiguous name **from the chain, not the bare token** (تمييز المهمل) — the classical method, implemented as layered, auditable evidence.
- 🔒 **Local‑first, offline, CPU‑only.** No external database, no cloud, no GPU. Your data never leaves your machine.
- 🩺 **Self‑auditing.** The system re‑checks every chain and every text against its own rules and surfaces what looks wrong — backed by **560+ automated tests**.
- 📚 **Built from the canonical library.** Six Books + the major musnads, ṣaḥīḥs and sunan, their commentaries, and nine biographical (رجال) sources — all downloaded and built locally.
- 🖥️ **A complete app**, not just a backend: a single‑file RTL interface that runs in the browser **and** as a native desktop window.

---

## Features in detail

### 🔎 Hybrid search
Lexical **and** semantic search fused with Reciprocal Rank Fusion (RRF) over **84,000+** traditions. Lexical search is SQLite FTS5 over a normalized matn (diacritics folded, hamza/alef/ya unified); semantic search is a 768‑dim Arabic sentence‑transformer. Results carry their grade and full citation, are grouped per hadith, and expose book/grade facets for filtering.

### 🧬 Isnād verification — the core engine
Given a chain, the system splits it on the transmission verbs, detects samāʿ/ʿanʿana and taḥwīl (ح), determines whether it reaches the Prophet ﷺ, and grades each narrator. The hard part — **identifying a narrator shared by several men** — is solved by a cascade of evidence, applied in order and each one auditable:

1. **قواعد التمييز** — the curated, classical rules a muḥaddith applies (e.g. «سفيان عن الأعمش = الثوري», «حماد عن أيوب = ابن زيد»).
2. **قرينة الرفقة** — the «company» heuristic: the candidate whose teachers/students best fit this chain wins, even over a confident bare‑name match.
3. **Corpus redundancy** — a narrator's recurring teacher across the corpus settles his identity.
4. **The documented network** — a directional teacher↔student graph mined from the رجال literature (تهذيب الكمال, الجرح والتعديل, الثقات): an ambiguous link is fixed to the homonym *documented* as a student of its resolved teacher, propagating to a fixpoint.
5. **Grade‑agreement gate** — when candidates *disagree* on the grade, the chain is **held (يُتوقَّف)**, never graded weak on a guess.
6. **The honest‑doubt node** — a genuine homonymy is presented as its closed set of possible identities (each with its grade), not collapsed to one.

A chain's verdict (الحكم على الإسناد) reports the weakest narrator, the transmission modes, and any حلقة held for doubt — conservatively, so a sound al‑Bukhārī chain of ثقات is never turned into «ضعيف» by a mere database gap.

### 👤 Narrator base (الرجال)
A **canonical** base of **23,000+** transmitters — **one record per man, deduplicated** across sources (the same person written two ways is merged; distinct namesakes are kept apart). Each record carries his grade, ṭabaqa, death year, kunya/nisba, teachers/students, and the **named verdicts of the critics** (أقوال الأئمة) — *who* said it, *what*, and *in which book*. Where critics differ on one man, the verdict takes **the lower of the two opinions** (أنزل القولين عند الاختلاف). Browse the whole base by letter and grade, or open any narrator's card.

### 🕸️ Takhrīj & structural ʿilal
Takhrīj gathers the parallel narrations of a matn, clusters them into wordings (verbatim / near / by‑meaning), and groups them under the Companion. Beyond *stated* defects, the system **detects candidate defects from the shape of the routes** — all as **hints to investigate, never rulings**:
- **تفرّد / غرابة** — a single Companion, or no corroborating route.
- **شذوذ** — a lone wording against the well‑attested many, **weighed by narrator grade** (a weaker narrator contradicting the stronger/more‑numerous = «شذوذٌ ظاهر»).
- **اضطراب** — many divergent wordings with no preponderant one.
- **اختلاف الرفع والوقف** & **الوصل والإرسال** — the routes split on reaching the Prophet ﷺ, or on a Companion having heard him.

### 📚 Library & reader
Browse the corpus by its own structure — collection → كتاب/باب → the hadiths under each — and the commentaries (شروح) alongside. Read any downloaded book natively (RTL text + in‑book search), or render a page range to a real Arabic PDF. A distraction‑free full‑screen reading mode is included.

### 🩺 Self‑audit
Five read‑only audits keep the system honest and measure every improvement:
- **audit_isnad** → flags Prophet‑graded (P), Companion‑mid‑chain (S), full‑name‑graded‑grave (W), and ambiguous (A) cases for review.
- **audit_matn** → empty/fragment, isnad‑in‑matn, grade‑tail, or non‑matn texts.
- **audit_conflicts** → a grave name (متروك/كذاب) colliding with a trustworthy namesake that could sink a sound chain.
- **audit_coverage** → how much of the chains the رجال base actually covers.
- **audit_nodes** → a parsing‑bug detector over every segmented chain.

### 🖥️ The interface
A single self‑contained HTML/JS/SVG file (no external libraries), right‑to‑left, served by the API and also wrapped in a native desktop window. Tabs for search, ask, takhrīj, the narrator card, the browse index, the library, the reader, isnād verification, and the audit/reference pages — plus three living reference pages (Methodology / Architecture / Technical) kept in sync with the code.

---

## How it's built — the pipeline

An 8‑step, idempotent, resumable pipeline turns raw books into the searchable corpus:

```
download (turath.io) → parse → index (FTS5) → narrator graph
        → rijal base → [optional AI extraction] → self-audit
```

Every step is safe to re‑run; a build replaces its output file atomically. A fresh clone builds everything with a single command — see **Install** below.

---

## Corpus & sources

**Ḥadīth:** Ṣaḥīḥ al‑Bukhārī · Ṣaḥīḥ Muslim · the four Sunan · al‑Muwaṭṭaʾ · Musnad Aḥmad · Ibn Khuzayma · Ibn Ḥibbān · al‑Mustadrak · al‑Dāraquṭnī — with major commentaries (Fatḥ al‑Bārī, Sharḥ al‑Nawawī, Tuḥfat al‑Aḥwadhī, ʿAwn al‑Maʿbūd…).

**Narrators:** Taqrīb al‑Tahdhīb · al‑Kāshif · Tahdhīb al‑Kamāl · al‑Jarḥ wa‑l‑Taʿdīl · al‑Iṣāba · al‑Thiqāt · Lisān al‑Mīzān · Siyar Aʿlām al‑Nubalāʾ · Tārīkh al‑Islām.

---

## Tech stack

**Python · FastAPI · SQLite** (FTS5 full‑text + vector BLOBs) · **sentence‑transformers** (Arabic, 768‑dim) · **pywebview** (desktop). No external DB, no cloud. The optional LLM layer (off / local / remote) is constrained to the retrieved sources and always cites. **560+ tests**, with CI running pytest + a UI syntax check on every push.

---

## By the numbers

| | |
|---|---|
| Indexed traditions | **84,000+** |
| Graded narrators | **23,000+** |
| Isnād coverage | **94%** |
| Biographical sources | **9** |
| Automated tests | **560+** |

---

## Roadmap

- A neural model for ʿilal/takhrīj *(needs a GPU)*
- A learned reranker for search
- A public server deployment
- More late‑period biographical sources

---

## Install

```bash
git clone https://github.com/a7medhosny92-cpu/hadith-research-backend
cd hadith-research-backend
./setup.sh            # Windows: setup.bat
```

`setup.sh` is self‑contained: it makes the virtual environment, installs the app, **downloads the books from turath.io, and builds the whole corpus** — then `uvicorn app.main:app` serves the UI at `http://localhost:8000/app` (or `python -m app.desktop` for the desktop window).

---

## License & ethics

The **code** is released under the **MIT License**. The **heritage texts** (matns and commentaries) remain the property of their rights‑holders and editors and are **not** covered by it. This is a research and study aid, not a substitute for qualified scholars.

—  ﴿ وَقُل رَّبِّ زِدْنِي عِلْمًا ﴾  —
