@echo off
REM Double-click to update the Hadith app: latest code + dependencies + corpus.
REM   update.bat              -> code + corpus
REM   update.bat --code-only  -> quick, code only
cd /d "%~dp0"
echo Tip: close the app window first, so the index files aren't locked.
echo.
".venv\Scripts\python.exe" -m scripts.update %*
echo.
pause
