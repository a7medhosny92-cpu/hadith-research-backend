@echo off
REM Double-click to update AND turn on "smart" (semantic) search:
REM   latest code + dependencies (incl. embeddings) + corpus + the vector index.
REM
REM The first run downloads an embedding model and embeds the whole corpus — a
REM one-off step that can take a while on a CPU-only laptop. Safe to re-run anytime
REM (resumable). Add --full to refresh the entire corpus, not just the canonical set.
cd /d "%~dp0"
echo Tip: close the app window first, so the index files aren't locked.
echo.
".venv\Scripts\python.exe" -m scripts.update --semantic %*
echo.
pause
