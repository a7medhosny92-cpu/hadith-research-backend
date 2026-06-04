# Viral Video Backend

Pipeline **end-to-end e completamente offline** che trasforma un semplice
argomento in un **video verticale** (1080×1920) pronto per TikTok / Reels /
Shorts: script → voce → frame → sottotitoli → `.mp4`.

Nessuna API a pagamento. Include:

- **Frontend web** servito da FastAPI (scrivi argomento → genera → anteprima → download)
- **Voce neurale Piper** (offline, naturale) con fallback automatico a espeak-ng
- **Immagini AI** opzionali via Stable Diffusion locale (stile `ai`) con fallback a slide
- **FFmpeg** per il montaggio e **Pillow** per la grafica

Ogni modulo è "pluggable": puoi sostituire i backend (es. un LLM locale per gli
script) senza riscrivere la pipeline.

## Cosa produce

Dato un argomento (es. *"la produttività"*) genera automaticamente:

- **Script** strutturato: Hook → N punti chiave → Call-to-action
- **Voce narrante** per ogni scena (TTS offline)
- **Frame verticali** 1080×1920 con badge, testo auto-dimensionato, dots di progresso
- **Sottotitoli** `.srt` sincronizzati con il parlato
- **Storyboard** (contact sheet) per l'anteprima rapida
- **Video finale** `video.mp4` (H.264 + AAC) con voce, sottotitoli a fuoco e
  musica opzionale
- **`script.json`** con titolo e hashtag ottimizzati

## Requisiti

```bash
# strumenti di sistema
apt-get install -y ffmpeg espeak-ng

# dipendenze Python
pip install -r requirements.txt

# voce neurale Piper (consigliata): scarica una voce italiana
python3 -m piper.download_voices it_IT-paola-medium --data-dir models/piper
```

> Senza `ffmpeg`/voce la pipeline funziona comunque e produce script,
> frame, storyboard e sottotitoli (salta solo voce e `.mp4`).

### Motore voce (TTS)

Selezione automatica (Piper se disponibile, altrimenti espeak-ng). Override:

```bash
export TTS_ENGINE=piper            # piper | espeak | auto (default)
export PIPER_DATA_DIR=models/piper # dove cercare le voci .onnx
```

### Immagini AI (Stable Diffusion, opzionale)

Richiede `torch`+`diffusers` e preferibilmente una GPU CUDA. Abilita con lo
stile `ai` (CLI `--style ai`, API `"style":"ai"`). Senza GPU/modello la
pipeline torna automaticamente alle slide a gradiente.

```bash
export SD_MODEL=stabilityai/sd-turbo  # modello (default)
export SD_DEVICE=cuda                 # cuda | cpu | auto
```

## Uso

### CLI

```bash
python3 cli.py "la produttività" --points 3 --lang it --seed 7 --out output/sample
# stile immagini AI (richiede GPU):
python3 cli.py "lo spazio" --style ai
# con musica di sottofondo opzionale:
python3 cli.py "il caffè" --music assets/musica.mp3
```

### Web app + API (FastAPI)

```bash
uvicorn app.main:app --reload
# poi apri http://localhost:8000 nel browser per l'interfaccia web
```

| Metodo | Endpoint | Descrizione |
|---|---|---|
| `GET`  | `/` | interfaccia web (frontend) |
| `GET`  | `/health` | stato + capacità (ffmpeg / tts / stable_diffusion) |
| `POST` | `/videos` | crea un job: `{"topic": "...", "num_points": 3, "lang": "it", "style": "slide"}` |
| `GET`  | `/videos/{id}` | stato del job + link agli artefatti |
| `GET`  | `/videos/{id}/files/{name}` | scarica un artefatto (es. `video.mp4`) |

Esempio:

```bash
curl -X POST localhost:8000/videos -H 'content-type: application/json' \
     -d '{"topic":"la produttività","num_points":3,"lang":"it"}'
# -> {"id":"abc123...","state":"queued",...}
curl localhost:8000/videos/abc123
# quando state == "done": scarica il video
curl -OJ localhost:8000/videos/abc123/files/video.mp4
```

## Struttura

```
app/
├── main.py              # API FastAPI + frontend
├── jobs.py              # job store in background (thread pool)
├── models.py            # schemi Pydantic
├── config.py            # configurazione via env
├── static/
│   └── index.html       # interfaccia web
└── pipeline/
    ├── script_gen.py    # argomento → script (hook/punti/cta)
    ├── tts.py           # testo → voce (Piper / espeak-ng)
    ├── visuals.py       # scena → frame 1080×1920 (Pillow)
    ├── image_gen.py     # sfondi AI opzionali (Stable Diffusion)
    ├── subtitles.py     # scene → .srt
    ├── assembler.py     # frame + voce + sottotitoli → .mp4 (ffmpeg)
    └── orchestrator.py  # pipeline end-to-end
cli.py                   # entry point a riga di comando
demo.py                  # demo offline (senza ffmpeg/tts)
tests/                   # pytest (salta gli stage senza i binari)
```

## Test

```bash
python3 -m pytest -q
```

I test che richiedono `ffmpeg`/`espeak-ng` vengono saltati automaticamente se i
binari non sono presenti.

## Estensioni future

- **Script migliori**: backend LLM locale (Ollama) dietro `script_gen.py`
- **Persistenza job**: Celery/RQ + Redis al posto del thread pool
- **B-roll video** reali al posto delle immagini statiche
