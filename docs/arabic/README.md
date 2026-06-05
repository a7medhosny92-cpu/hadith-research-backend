# Tutor di Arabo Classico/Coranico — Fondazione del sapere

Questa cartella contiene la **base di conoscenza** (il "spine" del sapere) su cui
costruiamo l'app-tutor interattiva per imparare l'arabo classico/coranico.

## File
- **`knowledge-base.md`** — il documento di conoscenza strutturato (fonetica/tajwīd,
  ortografia, ṣarf, naḥw, balāgha, lessico coranico, curriculum a livelli, errori
  tipici, disaccordi tra scuole). Sintesi di una ricerca multi-fonte verificata.
- **`sources.md`** — elenco delle fonti consultate (متون classici + accademiche moderne).

## Stato delle fasi

```
[Fase 1] ✅ base di conoscenza        → docs/arabic/*.md
[Fase 2] ✅ dati strutturati          → app/arabic/knowledge/*.json
[Fase 3] ✅ motore linguistico        → app/arabic/{phonology,tajweed,morphology,iraab}.py
[Fase 4] ⏳ cervello ibrido           → predisposto offline; aggancio LLM da fare
[Fase 5] 🔄 finestra interattiva      → app/arabic/web.py + static/index.html (avviata)
```

## Avviare il tutor (finestra interattiva)

```bash
pip install -r requirements.txt
uvicorn app.arabic.web:app --reload      # poi apri http://localhost:8000
# CLI equivalente:
python3 arabic_cli.py iraab "إِنَّ اللَّهَ غَفُورٌ"
python3 arabic_cli.py conjugate ك ت ب 1
python3 arabic_cli.py tajweed "بِسْمِ اللَّهِ"
python3 arabic_cli.py letter ض
```

La finestra ha 6 sezioni: **الحروف** (lettere: makhraj+ṣifāt), **التجويد** (analizzatore),
**الصرف** (coniugatore I–X + mushtaqqāt), **الإعراب** (analisi + correzione ✓/✗),
**المستويات** (curriculum), **المفردات** (lessico per radice).

## Principi guida (dalla ricerca)
- **Iʿrāb come spina dorsale**: l'analisi dei casi attraversa ogni livello.
- **Lessico per radice e per frequenza**: ~125 parole ≈ 50% del Corano, ~300–500 radici
  ≈ 75–85%; insegnare prima le parole-funzione.
- **Tre scienze in parallelo** (naḥw + ṣarf + balāgha), non in sequenza rigida.
- **Onestà sulle divergenze**: il tutor segnala i punti dibattuti (es. polarità
  dell'العدد, lunghezze del madd per qirāʾa) invece di presentarli come assoluti.
- **Riuso degli asset esistenti**: diacritizzazione tashkīl, motore `nahw.py`, voci
  TTS arabe Piper costruiti nelle fasi precedenti.
