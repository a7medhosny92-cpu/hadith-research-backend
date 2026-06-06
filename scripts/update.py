"""Self-update the local install from GitHub.

Pulls the latest code, refreshes dependencies, and (by default) brings the corpus
up to date: download new/updated books -> parse -> rebuild the search indexes.

    python -m scripts.update              # code + corpus (full sync)
    python -m scripts.update --code-only  # just pull code + refresh deps (fast)
    python -m scripts.update --full       # refresh the FULL corpus, not just canonical

Safe to re-run anytime: ``git pull`` is fast-forward only, the crawl is resumable,
and parse/index are idempotent. On Windows you can also double-click ``update.bat``.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def step(title: str, cmd: list[str]) -> None:
    print(f"\n=== {title} ===\n$ {' '.join(cmd)}")
    if subprocess.run(cmd, cwd=ROOT).returncode != 0:
        print(f"\n[!] Step failed: {title}\n    Fix the issue above, then run the update again.")
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="Update the local install from GitHub.")
    ap.add_argument("--code-only", action="store_true",
                    help="only pull code + refresh dependencies (skip the corpus rebuild)")
    ap.add_argument("--full", action="store_true",
                    help="refresh the FULL corpus (all categories), not just the canonical set")
    ap.add_argument("--semantic", action="store_true",
                    help="also (re)build the semantic vector index for «smart» search "
                         "(installs the 'embeddings' extra; the first run downloads a model)")
    args = ap.parse_args()

    step("1/5  Pull the latest code from GitHub", ["git", "pull", "--ff-only"])
    # Include the desktop window (pywebview) and the LLM switch (litellm) so the app
    # and the local/remote «brain» work out of the box after an update; add the
    # embeddings stack too when semantic search is requested.
    extras = ".[dev,desktop,llm,embeddings]" if args.semantic else ".[dev,desktop,llm]"
    step("2/5  Refresh dependencies", [PY, "-m", "pip", "install", "-e", extras, "-q"])

    if args.code_only:
        print("\nDone — code is up to date. (Re-run without --code-only to refresh the corpus too.)")
        return

    ingest = [PY, "-X", "utf8", "-m", "scripts.ingest"]
    ingest += (["--categories", "6", "7", "8", "9", "10", "26"] if args.full
               else ["--priority", "--with-commentaries"])
    step("3/7  Download new/updated books (resumable — may take a while)", ingest)
    step("4/7  Parse raw pages into structured JSONL", [PY, "-X", "utf8", "-m", "scripts.parse"])
    step("5/7  Rebuild the search indexes", [PY, "-X", "utf8", "-m", "scripts.index"])
    step("6/7  Build the narrator network", [PY, "-X", "utf8", "-m", "scripts.build_graph"])
    # Full narrator gradings (تقريب التهذيب + الكاشف) → decisive isnad verdicts. Downloads
    # the small رجال sources if missing; resumable and idempotent.
    step("7/7  Build the رجال gradings (تقريب التهذيب + الكاشف)",
         [PY, "-X", "utf8", "-m", "scripts.build_rijal"])
    if args.semantic:
        step("+ semantic  Build the vector index (incremental — embeds only new/changed matns)",
             [PY, "-X", "utf8", "-m", "scripts.embed"])
    print("\nDone — code, corpus and indexes are all up to date.")


if __name__ == "__main__":
    main()
