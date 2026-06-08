# تهذيب الكمال (al-Mizzī) — book study & extractor spec

Empirical study of book **3722 (8,258 entries)** to design a prose رجال extractor (ROADMAP #8).
Goal: full names + **شيوخ/تلاميذ network** + **multi-critic verdicts** → resolve the audit's «مشترك»
(A) homonyms and correct the متروك/كذاب (W) mis-grades.

## Coverage (of 8,258 entries)
- **94%** carry رموز (the Six-Books symbols) · **91%** have «روى عن» (شيوخ) · **89%** «روى عنه» (تلاميذ)
- ~22% an explicit death year (مات/توفي سنة) · ~670 Companions (له صحبة / صحابي)

## Entry format
```
NNNN - رموز :  full name + nasab + nisba + kunya
رَوَى عَن :   شيخ (رموز)، شيخ (رموز)، …
رَوَى عَنه :  تلميذ (رموز)، …
   قال [transmitter] عن [critic]: [verdict]   e.g. «قال أبو طالب عن أحمد: لا بأس به»
   وقال [critic]: [verdict]                     «قال ابن معين: صدوق»، «قال النسائي: ضعيف … ليس بثقة»
مات/توفي سنة [year]
روى له [الكتب الستة] / وروى له الباقون سوى …
```

## رموز vocabulary (book symbols)
خ=Bukhārī · م=Muslim · د=Abū Dāwūd · ت=Tirmidhī · س=Nasāʾī · ق=Ibn Mājah · **ع=all six (الجماعة)** ·
٤=the four Sunan · بخ=Bukhārī (Adab al-mufrad) · خت=Bukhārī taʿlīqan · سي=Nasāʾī (ʿamal al-yawm) ·
مد/قد=Abū Dāwūd (marāsīl/qadar) · عخ · عس · فق · كن · لت · تم · ص · كد · **تمييز** = a man listed only
to disambiguate (NOT one of the Six Books' narrators).
→ **A man with خ or م cannot be متروك/كذاب** — the rumūz alone correct several W-category errors.

## The hard part — editor footnotes — and the clean fix
Footnotes are pervasive: **17,786** «____» blocks and **125,781** «(N)» inline refs (>15 per entry).
They discuss OTHER men, so an unstripped «متروك» in a footnote would poison a ثقة man's grade. BUT
each raw page is laid out «main text  ____  footnotes»: **cut every page at the first «____» run** to
drop the footnotes reliably, then strip inline «(N)» refs. (Validated against the raw page structure.)

## Extractor spec
1. **Footnotes:** per page, keep only the text *before* the first «____»; then strip inline «(N)».
2. **Head:** number + رموز (books) + full name + kunya.
3. **Network:** شيوخ from the «روى عن:» block, تلاميذ from «روى عنه:» (comma-separated, each w/ rumūz).
4. **Verdicts:** «قال [critic]: [verdict]» / «وقال …» → (critic, verdict) pairs.
5. **Death:** «مات/توفي سنة [year]».

## Validation so far
A prototype parsed all 8,258 entries; the رموز confirm the audit's W-errors are wrong:
عثمان بن أبي شيبة (3857 · خ م ق), يونس بن محمد (7184 · ع), المحاربي (3949 · ع) — all in the Six Books,
so none can be «متروك»/«كذاب».

## Status / next
Book on hand: the user's zip → `data/raw/turath/books/3722.json` (gitignored, ephemeral — the user can
re-provide the zip). Next: build the extractor (footnote-strip → head → network → verdicts), test it
on the book here, then integrate as a rich rijal source + into the narrator graph (build_graph) so the
شيوخ/تلاميذ resolve the «مشترك» homonyms at verdict time.
