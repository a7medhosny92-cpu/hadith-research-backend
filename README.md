# Viral Video Backend

Pipeline **end-to-end e completamente offline** che trasforma un semplice
argomento in un **video verticale** (1080×1920) pronto per TikTok / Reels /
Shorts: script → voce → frame → sottotitoli → `.mp4`.

Nessuna API a pagamento. Include:

- **Frontend web** servito da FastAPI (scrivi argomento → genera → anteprima → download)
- **4 template**: `classic`, `quiz`, `top5`, `storytelling` (strutture e palette diverse)
- **Scene dinamiche**: movimento Ken Burns (zoom/pan), **crossfade veri** tra le scene
  e **testo animato karaoke** sincronizzato con la voce
- **Multilingua**: script, sottotitoli e hashtag in `it` / `en` / `es` / **`ar` (arabo
  RTL)** (altre lingue via TTS), con shaping e bidi corretti
- **Selettore di voce**: più voci neurali per lingua, scelta da CLI / API / web
- **B-roll**: usa clip video locali (`assets/broll/`) come sfondo in movimento
- **Voce neurale Piper** (offline, naturale) con fallback automatico a espeak-ng
- **Immagini AI** opzionali via Stable Diffusion locale (stile `ai`) con fallback a slide
- **Docker**: build e avvio con un comando
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
# strumenti di sistema (libraqm + font Noto servono per l'arabo/RTL)
apt-get install -y ffmpeg espeak-ng fonts-noto-core libraqm0

# dipendenze Python
pip install -r requirements.txt

# voci neurali Piper (consigliate): scarica it, en, es, ar
python3 scripts/download_voices.py it en es ar
# tutte le voci di una lingua (per il selettore):
python3 scripts/download_voices.py --all it en
```

> Senza `ffmpeg`/voce la pipeline funziona comunque e produce script,
> frame, storyboard e sottotitoli (salta solo voce e `.mp4`).

### Docker (tutto incluso)

```bash
docker build -t viral-video .
docker run -p 8000:8000 viral-video
# apri http://localhost:8000
```

L'immagine include FFmpeg, espeak-ng e la voce Piper italiana.

### Lingue e voce (TTS)

Lo script viene scritto nella lingua scelta (pacchetti completi `it`, `en`, `es`,
`ar` in `app/pipeline/i18n.py`; le altre usano testi inglesi come fallback).
L'**arabo** è RTL: viene reso con shaping e ordine bidi corretti (via libraqm in
Pillow). Poiché libass impagina il karaoke `\k` da sinistra a destra ignorando il
bidi (invertendo le parole), per le lingue RTL la didascalia viene "bakeata" nel
fotogramma — corretta e statica — mantenendo comunque movimento e crossfade.

Ogni lingua può avere più voci neurali Piper, selezionabili (`--voice`, campo
`voice` nell'API, menu nel frontend). `GET /voices` elenca quelle scaricate. Se
una voce non è disponibile si ripiega su espeak-ng.

```bash
python3 scripts/download_voices.py it en es ar         # voce di default per lingua
python3 scripts/download_voices.py --all it            # tutte le voci italiane
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
# template diversi:
python3 cli.py "il caffè" --template quiz
python3 cli.py "lo spazio" --template top5
python3 cli.py "la disciplina" --template storytelling
# multilingua (it/en/es/ar completi, altre lingue via TTS):
python3 cli.py "productivity" --lang en
python3 cli.py "productividad" --lang es
python3 cli.py "الإنتاجية" --lang ar          # arabo (RTL)
# selettore di voce:
python3 cli.py --list-voices                  # elenca le voci scaricate
python3 cli.py "il caffè" --voice it_IT-riccardo-x_low
# transizioni: crossfade vero (default) o stacco netto:
python3 cli.py "la produttività" --transition cut
# scene statiche (niente movimento/karaoke):
python3 cli.py "la produttività" --no-animate
# sfondo b-roll (clip in assets/broll/) e immagini AI (richiede GPU):
python3 cli.py "il mare" --broll
python3 cli.py "lo spazio" --style ai
# musica di sottofondo opzionale:
python3 cli.py "il caffè" --music assets/musica.mp3
```

Template: `classic`, `quiz`, `top5`, `storytelling`. Lingue complete: `it`, `en`,
`es`, `ar` (le altre usano comunque la voce TTS, con testi in inglese come fallback).

### Web app + API (FastAPI)

```bash
uvicorn app.main:app --reload
# poi apri http://localhost:8000 nel browser per l'interfaccia web
```

| Metodo | Endpoint | Descrizione |
|---|---|---|
| `GET`  | `/` | interfaccia web (frontend) |
| `GET`  | `/health` | stato + capacità (ffmpeg / tts / stable_diffusion) |
| `GET`  | `/voices` | voci scaricate per lingua (per il selettore) |
| `POST` | `/videos` | crea un job: `{"topic":"...","template":"top5","lang":"ar","voice":null,"style":"slide","animate":true,"transition":"crossfade","broll":false}` |
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
    ├── templates.py     # template: classic / quiz / top5 / storytelling
    ├── i18n.py          # language pack (it / en / es / ar) per gli script
    ├── tts.py           # testo → voce (Piper / espeak-ng), catalogo voci per lingua
    ├── visuals.py       # scena → frame 1080×1920 (Pillow)
    ├── image_gen.py     # sfondi AI opzionali (Stable Diffusion)
    ├── broll.py         # clip b-roll locali come sfondo
    ├── subtitles.py     # scene → .srt + .ass (karaoke), timeline crossfade
    ├── assembler.py     # montaggio ffmpeg: Ken Burns + crossfade (xfade)
    └── orchestrator.py  # pipeline end-to-end
assets/broll/            # metti qui le tue clip b-roll
scripts/download_voices.py  # scarica le voci Piper per lingua
cli.py                   # entry point a riga di comando
demo.py                  # demo offline (senza ffmpeg/tts)
Dockerfile               # build/run con un comando
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
