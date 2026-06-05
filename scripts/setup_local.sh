#!/usr/bin/env bash
# Build the local corpus end-to-end: download from turath.io → parse → index.
#
# Run this ON YOUR OWN MACHINE: the corpus lands under data/ and stays there
# (your disk is permanent — unlike an ephemeral cloud container). It is fully
# RESUMABLE: if it stops or you close the laptop, just run it again and it
# continues from where it left off.
#
# Usage:
#   bash scripts/setup_local.sh [canonical|core|full]
#
#   canonical  (default)  core collections (Bukhārī, Muslim, the Sunan, Musnad
#                         Aḥmad, …) + their main commentaries (شروح: Fatḥ al-Bārī,
#                         Sharḥ al-Nawawī, …), full. ~2–3 GB, several hours.
#   core                  the core collections only, no commentaries — lighter/faster.
#   full                  every hadith-sciences category (~2.9M pages — tens of GB,
#                         days). Heavy for a normal laptop.
set -euo pipefail

cd "$(dirname "$0")/.."             # run from the project root, wherever invoked
PYTHON="${PYTHON:-python}"
SCOPE="${1:-canonical}"

case "$SCOPE" in
  canonical) INGEST_ARGS=(--priority --with-commentaries) ;;
  core)      INGEST_ARGS=(--priority) ;;
  full)      INGEST_ARGS=(--categories 6 7 8 9 10 26) ;;
  *) echo "Unknown scope '$SCOPE' (use: canonical | core | full)" >&2; exit 2 ;;
esac

echo "▶ Scope: $SCOPE"
if ! "$PYTHON" -c "import app" >/dev/null 2>&1; then
  echo "  The project isn't installed in this Python. Once, set it up:" >&2
  echo "    python -m venv .venv && source .venv/bin/activate && pip install -e \".[dev]\"" >&2
  exit 1
fi

echo "▶ 1/3  Downloading from turath.io (polite + resumable — rerun to continue)…"
"$PYTHON" -m scripts.ingest "${INGEST_ARGS[@]}"

echo "▶ 2/3  Parsing raw pages → structured JSONL (hadith + شروح)…"
"$PYTHON" -m scripts.parse

echo "▶ 3/3  Building the sqlite search indexes…"
"$PYTHON" -m scripts.index

echo "✅ Done. The corpus + indexes are under data/ and stay on this machine."
echo "   Run the app:  uvicorn app.main:app --reload   →  http://localhost:8000/docs"
