"""Text-to-speech: a line of text becomes a WAV file.

Two fully-offline backends, selected automatically (best first):

  1. Piper  - neural TTS, very natural voice (preferred)
  2. espeak-ng - lightweight robotic fallback

Override with env vars:
  TTS_ENGINE = piper | espeak | auto   (default: auto)
  PIPER_MODEL = path to a .onnx voice  (default: models/piper/<lang voice>)

The public `synthesize` / `available` / `wav_duration` API is unchanged, so the
rest of the pipeline does not care which engine is used.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import wave
from pathlib import Path

ESPEAK = shutil.which("espeak-ng") or shutil.which("espeak")

# Default Piper voices per language (looked up under PIPER_DATA_DIR).
# Download with: python3 -m piper.download_voices <voice> --data-dir models/piper
_PIPER_DEFAULT_VOICE = {
    "it": "it_IT-paola-medium",
    "en": "en_US-amy-medium",
    "es": "es_ES-davefx-medium",
    "fr": "fr_FR-siwis-medium",
    "de": "de_DE-thorsten-medium",
    "pt": "pt_BR-faber-medium",
}
PIPER_DATA_DIR = Path(os.getenv("PIPER_DATA_DIR", "models/piper"))


class TTSUnavailable(RuntimeError):
    pass


def _piper_model_for(lang: str) -> Path | None:
    explicit = os.getenv("PIPER_MODEL")
    if explicit:
        p = Path(explicit)
        return p if p.exists() else None
    voice = _PIPER_DEFAULT_VOICE.get(lang)
    if not voice:
        return None
    p = PIPER_DATA_DIR / f"{voice}.onnx"
    return p if p.exists() else None


def _piper_importable() -> bool:
    try:
        import piper  # noqa: F401
        return True
    except Exception:
        return False


def engine(lang: str = "it") -> str:
    """Resolve which backend will actually be used for `lang`."""
    choice = os.getenv("TTS_ENGINE", "auto").lower()
    piper_ok = _piper_importable() and _piper_model_for(lang) is not None
    if choice == "piper":
        return "piper" if piper_ok else "none"
    if choice == "espeak":
        return "espeak" if ESPEAK else "none"
    # auto: prefer piper, then espeak
    if piper_ok:
        return "piper"
    if ESPEAK:
        return "espeak"
    return "none"


def available(lang: str = "it") -> bool:
    return engine(lang) != "none"


def _synthesize_piper(text: str, out_path: Path, lang: str) -> Path:
    model = _piper_model_for(lang)
    cmd = ["python3", "-m", "piper", "-m", str(model), "-f", str(out_path)]
    subprocess.run(cmd, input=text.encode("utf-8"), check=True, capture_output=True)
    return out_path


def _synthesize_espeak(text: str, out_path: Path, lang: str,
                       words_per_minute: int, pitch: int) -> Path:
    if not ESPEAK:
        raise TTSUnavailable("espeak-ng/espeak non trovato.")
    cmd = [ESPEAK, "-v", lang, "-s", str(words_per_minute), "-p", str(pitch),
           "-w", str(out_path), text]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def synthesize(text: str, out_path: Path, lang: str = "it",
               words_per_minute: int = 165, pitch: int = 45) -> Path:
    """Render `text` to a WAV using the best available offline engine."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    eng = engine(lang)
    if eng == "piper":
        return _synthesize_piper(text, out_path, lang)
    if eng == "espeak":
        return _synthesize_espeak(text, out_path, lang, words_per_minute, pitch)
    raise TTSUnavailable(
        "Nessun motore TTS disponibile. Installa piper-tts + una voce, "
        "oppure: apt-get install espeak-ng")


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())
