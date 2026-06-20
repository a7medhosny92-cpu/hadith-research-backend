@echo off
REM ---------------------------------------------------------------------------
REM First-time setup (Windows) - one double-click. Creates a virtual environment,
REM installs the app, DOWNLOADS the books from turath.io, and builds the whole
REM local corpus (parse -> index -> narrator graph -> rijal base -> self-audits).
REM
REM   setup.bat              core install (lexical search, isnad verification)
REM   setup.bat --semantic   also build the "smart" semantic search (downloads a model)
REM   setup.bat --full       download the FULL corpus, not just the canonical set
REM
REM Safe to re-run: the download is resumable and every build step is idempotent.
REM ---------------------------------------------------------------------------
cd /d "%~dp0"

echo ==^> Creating the virtual environment (.venv)
py -3 -m venv .venv || python -m venv .venv

echo ==^> Installing the app and its dependencies
".venv\Scripts\python.exe" -m pip install -U pip -q
".venv\Scripts\python.exe" -m pip install -e ".[dev,desktop]" -q

echo ==^> Downloading the books and building the corpus (resumable; may take a while)
".venv\Scripts\python.exe" -m scripts.update --no-git %*

echo.
echo Setup complete. Start the app:
echo    .venv\Scripts\python.exe -m app.desktop
echo    ( or:  .venv\Scripts\python.exe -m uvicorn app.main:app   then open http://localhost:8000/app )
echo.
pause
