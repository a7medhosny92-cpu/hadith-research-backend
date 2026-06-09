"""Self-update the local install from GitHub.

Pulls the latest code, refreshes dependencies, and (by default) brings the corpus
up to date: download new/updated books -> parse -> rebuild the search indexes.

    python -m scripts.update              # code + corpus (full sync)
    python -m scripts.update --code-only  # just pull code + refresh deps (fast)
    python -m scripts.update --full       # refresh the FULL corpus, not just canonical

Once the semantic index exists, every update re-embeds **incrementally** (only the
matns whose text changed) to keep it aligned with the freshly-rebuilt id space — so
``update.bat`` and ``update-semantic.bat`` both leave search consistent.

Safe to re-run anytime: ``git pull`` is fast-forward only, the crawl is resumable,
and parse/index are idempotent. On Windows you can also double-click ``update.bat``.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from app.config import get_settings

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def step(title: str, cmd: list[str], *, fatal: bool = True) -> None:
    print(f"\n=== {title} ===\n$ {' '.join(cmd)}")
    if subprocess.run(cmd, cwd=ROOT).returncode != 0:
        if not fatal:
            # an optional step (e.g. the LLM pass with no engine / books not yet downloaded) must not
            # break the update — the pipeline falls back to the regex path (the LLM fold-in is gated).
            print(f"\n[~] Optional step skipped: {title} — continuing without it.")
            return
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
    ap.add_argument("--llm", action="store_true",
                    help="run the LLM extraction (rijal network + chain segmentation) before parsing")
    ap.add_argument("--no-llm", action="store_true",
                    help="skip the LLM extraction even if an engine is configured")
    args = ap.parse_args()

    settings = get_settings()
    # Keep the semantic index aligned automatically: once it's been built, a re-index
    # reassigns row ids, so every update must re-embed (incrementally — fast). --semantic
    # forces it on (and installs the embeddings extra) for the first-time setup.
    semantic = args.semantic or settings.vector_index_path.exists()
    # The LLM extraction (scripts.build_rijal_llm) is folded in like auto-semantic: it runs whenever
    # an LLM engine is configured (`llm_default_engine != off`) — so «we use LLM» simply happens —
    # producing the rijal+network and clean-chain files the (gated) pipeline then consumes. Faithful,
    # cached and resumable, so re-runs are cheap; --llm / --no-llm force it on / off.
    run_llm = (args.llm or settings.llm_default_engine != "off") and not args.no_llm

    # Always update from main, even if a previous session left the checkout on another
    # branch — otherwise `git pull` would fast-forward the wrong branch and silently miss
    # the latest code. (Local data lives under data/, which is gitignored, so switching is safe.)
    step("1/8  Switch to the main branch", ["git", "checkout", "main"])
    step("2/8  Pull the latest code from GitHub", ["git", "pull", "--ff-only"])
    # Include the desktop window (pywebview) and the LLM switch (litellm) so the app
    # and the local/remote «brain» work out of the box after an update; add the
    # embeddings stack too when semantic search is in use.
    extras = ".[dev,desktop,llm,embeddings]" if semantic else ".[dev,desktop,llm]"
    step("3/8  Refresh dependencies", [PY, "-m", "pip", "install", "-e", extras, "-q"])

    if args.code_only:
        print("\nDone — code is up to date. (Re-run without --code-only to refresh the corpus too.)")
        return

    ingest = [PY, "-X", "utf8", "-m", "scripts.ingest"]
    ingest += (["--categories", "6", "7", "8", "9", "10", "26"] if args.full
               else ["--priority", "--with-commentaries"])
    step("4/8  Download new/updated books (resumable — may take a while)", ingest)
    # LLM extraction BEFORE parse, so parse/build_rijal/build_graph all see the data. The FIRST run
    # is heavy (one call per tarjama / per suspicious chain) but cached & resumable — re-runs are
    # cheap, and every record is faithfulness-validated (an unfaithful answer falls back to the regex).
    if run_llm:
        llm = [PY, "-X", "utf8", "-m", "scripts.build_rijal_llm"]
        eng = ["--engine", "remote"] if settings.llm_default_engine == "off" else []
        step("+ LLM رجال  (شيوخ/تلاميذ network + grades — faithful, cached)",
             llm + ["--mode", "rijal"] + eng, fatal=False)
        step("+ LLM إسناد  (re-segment only the chains the regex mis-split — faithful, cached)",
             llm + ["--mode", "chains"] + eng, fatal=False)
    step("5/8  Parse raw pages into structured JSONL", [PY, "-X", "utf8", "-m", "scripts.parse"])
    step("6/8  Rebuild the search indexes", [PY, "-X", "utf8", "-m", "scripts.index"])
    step("7/8  Build the narrator network", [PY, "-X", "utf8", "-m", "scripts.build_graph"])
    # Full narrator gradings (تقريب التهذيب + الكاشف) → decisive isnad verdicts. Downloads
    # the small رجال sources if missing; resumable and idempotent.
    step("8/8  Build the رجال gradings (تقريب التهذيب + الكاشف)",
         [PY, "-X", "utf8", "-m", "scripts.build_rijal"])
    if semantic:
        why = "" if args.semantic else " (keeping your existing semantic index aligned)"
        step(f"+ semantic  Build the vector index — incremental, only new/changed matns{why}",
             [PY, "-X", "utf8", "-m", "scripts.embed"])
    # Refresh the isnad-audit report (the «التدقيق» review tab) so it reflects the new data.
    step("+ تدقيق  Build the isnad audit report (review tab)",
         [PY, "-X", "utf8", "-m", "scripts.audit_isnad"])
    print(f"\nDone — code, corpus and indexes are all up to date"
          f"{' (incl. the LLM rijal + chains)' if run_llm else ''}.")


if __name__ == "__main__":
    main()
