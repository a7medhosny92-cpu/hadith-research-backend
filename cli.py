"""Command-line entry point: render a full video from a topic.

    python3 cli.py "la produttività" --points 3 --lang it --out output/cli
"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.pipeline.orchestrator import create_video


def main() -> None:
    ap = argparse.ArgumentParser(description="Genera un video virale verticale da un argomento.")
    ap.add_argument("topic", help="Argomento del video")
    ap.add_argument("--points", type=int, default=3, help="Numero di punti chiave (1-5)")
    ap.add_argument("--lang", default="it", help="Lingua TTS (it, en, ...)")
    ap.add_argument("--seed", type=int, default=None, help="Seed riproducibile")
    ap.add_argument("--style", choices=["slide", "ai"], default="slide",
                    help="Stile visivo: slide (gradienti) o ai (Stable Diffusion)")
    ap.add_argument("--music", default=None, help="File audio di sottofondo (opzionale)")
    ap.add_argument("--out", default="output/cli", help="Cartella di output")
    args = ap.parse_args()

    def progress(stage: str, pct: float) -> None:
        print(f"  [{pct*100:5.1f}%] {stage}")

    music = Path(args.music) if args.music else None
    result = create_video(
        topic=args.topic, workdir=Path(args.out), num_points=args.points,
        lang=args.lang, music=music, seed=args.seed, style=args.style,
        progress=progress,
    )

    print("\n  TITOLO :", result.script.title)
    print("  HASHTAG:", " ".join(result.script.hashtags))
    if result.video:
        print("  VIDEO  :", result.video)
    print("  FRAME  :", len(result.frames), "->", result.workdir)
    for w in result.warnings:
        print("  ! ", w)


if __name__ == "__main__":
    main()
