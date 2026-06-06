@echo off
REM Double-click to update the Hadith app: latest code + dependencies + corpus.
REM   update.bat              -> code + corpus
REM   update.bat --code-only  -> quick, code only
cd /d "%~dp0"
".venv\Scripts\python.exe" -m scripts.update %*
echo.
pause
