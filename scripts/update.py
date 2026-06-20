"""Self-update the local install from GitHub.

Pulls the latest code, refreshes dependencies, and (by default) brings the corpus
up to date: download new/updated books -> parse -> rebuild the search indexes.

    python -m scripts.update              # code + corpus (full sync)
    python -m scripts.update --no-git     # FRESH CLONE / offline: skip git, just download + build
    python -m scripts.update --code-only  # just pull code + refresh deps (fast)
    python -m scripts.update --full       # refresh the FULL corpus, not just canonical
    python -m scripts.update --llm-rijal  # also run the optional (marginal) LLM رجال grade pass

For a brand-new clone, prefer the one-command ``./setup.sh`` (Windows: ``setup.bat``) — it makes the
venv, installs the app, then runs this with ``--no-git`` to download the books and build everything.

When an LLM engine is configured (``LLM_DEFAULT_ENGINE=local``), every update also runs a
faithful, cached LLM pass that re-segments the few chains the regex mis-splits — the recovered
narrators feed the narrator network. The رجال grade pass is OFF by default (the terse تقريب/الكاشف
carry no شيوخ/تلاميذ network, so the regex already covers them); opt in with ``--llm-rijal``.

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
    ap.add_argument("--no-git", action="store_true",
                    help="skip the git checkout/pull — build the corpus from the code as-is "
                         "(for a FRESH CLONE / first-time setup, or an offline rebuild)")
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
    ap.add_argument("--llm-rijal", action="store_true",
                    help="also run the (marginal) LLM رجال pass — off by default: تقريب/الكاشف are "
                         "terse grade-books with no شيوخ/تلاميذ network, so the regex already covers them")
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
    # --no-git skips this: a fresh clone (or an offline machine) just builds the code as-is.
    if not args.no_git:
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
    # is heavy (one call per suspicious chain) but cached & resumable — re-runs are cheap, and every
    # record is faithfulness-validated (an unfaithful answer falls back to the regex).
    if run_llm:
        # Always extract with the dedicated model (settings.llm_extract_model — gemma4:31b-cloud
        # by default, reached through the local Ollama daemon), independent of the /ask «brain»,
        # so extraction quality never depends on what local/remote happen to be set to in .env.
        llm = [PY, "-X", "utf8", "-m", "scripts.build_rijal_llm", "--model", settings.llm_extract_model]
        # CHAINS is the LLM's unique value: it re-segments only the chains the regex mis-split (matn
        # leaked into the isnad, a verse, 0 narrators). The recovered narrators then feed build_graph's
        # network — so the chain pass actually STRENGTHENS «the link», it doesn't replace it.
        step("+ LLM إسناد  (re-segment only the chains the regex mis-split — faithful, cached)",
             llm + ["--mode", "chains"], fatal=False)
        # The رجال pass is OFF by default (opt in with --llm-rijal): تقريب/الكاشف are terse grade-books
        # with no شيوخ/تلاميذ lists, so the LLM only re-derives grades the regex already has and builds
        # no link. The network comes from the corpus chains + the regex tahdhib/jarh extractors.
        if args.llm_rijal:
            step("+ LLM رجال  (grades only — تقريب/الكاشف have no network; opt-in)",
                 llm + ["--mode", "rijal"], fatal=False)
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
    # …and the matn-audit report (the «تدقيق المتون» review tab): flag every extracted matn that
    # looks empty/truncated, isnad-leaked, grade-tailed, or non-matn.
    step("+ تدقيق المتون  Build the matn audit report (review tab)",
         [PY, "-X", "utf8", "-m", "scripts.audit_matn"])
    # …and the رجال-conflict report (the «تعارض الرجال» tab): grave↔trustworthy name collisions, so any
    # new clash that could grade a sound chain by the wrong man is caught the moment it appears.
    step("+ تعارض الرجال  Build the narrator-conflict report (review tab)",
         [PY, "-X", "utf8", "-m", "scripts.audit_conflicts"])
    tail = (" (incl. the LLM chain re-segmentation" + (" + رجال" if args.llm_rijal else "") + ")") if run_llm else ""
    print(f"\nDone — code, corpus and indexes are all up to date{tail}.")


if __name__ == "__main__":
    main()
