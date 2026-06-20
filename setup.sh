#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# First-time setup — one command. Creates a virtual environment, installs the
# app, DOWNLOADS the books from turath.io, and builds the whole local corpus
# (parse → index → narrator graph → rijal base → self-audits).
#
#   ./setup.sh                 # core install (lexical search, isnad verification)
#   ./setup.sh --semantic      # also build the «smart» semantic search (downloads a model)
#   ./setup.sh --full          # download the FULL corpus, not just the canonical set
#
# Safe to re-run anytime — the download is resumable and every build step is
# idempotent. When it finishes, start the app with the command it prints.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
echo "==> Creating the virtual environment (.venv)"
"$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Installing the app and its dependencies"
python -m pip install -U pip -q
python -m pip install -e ".[dev,desktop]" -q

echo "==> Downloading the books and building the corpus (resumable; may take a while)"
python -m scripts.update --no-git "$@"

cat <<'DONE'

✅ Setup complete.

Start the app:
  source .venv/bin/activate
  uvicorn app.main:app            # then open  http://localhost:8000/app
  # …or the native desktop window:
  python -m app.desktop

To refresh later (more books / newer code):  python -m scripts.update
DONE
