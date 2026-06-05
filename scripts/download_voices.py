"""Download Piper voices for one or more languages.

    python3 scripts/download_voices.py it en es
    python3 scripts/download_voices.py            # downloads the default set

Voices are saved under PIPER_DATA_DIR (default: models/piper) and picked up
automatically by the TTS engine.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline.tts import _PIPER_DEFAULT_VOICE, PIPER_DATA_DIR

DEFAULT_LANGS = ["it", "en", "es"]


def main(langs: list[str]) -> None:
    PIPER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for lang in langs:
        voice = _PIPER_DEFAULT_VOICE.get(lang)
        if not voice:
            print(f"  ! nessuna voce di default per '{lang}', salto")
            continue
        print(f"  scarico {lang} -> {voice} ...")
        subprocess.run(
            [sys.executable, "-m", "piper.download_voices", voice,
             "--data-dir", str(PIPER_DATA_DIR)],
            check=True)
    print(f"  fatto. Voci in {PIPER_DATA_DIR}/")


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT_LANGS)
