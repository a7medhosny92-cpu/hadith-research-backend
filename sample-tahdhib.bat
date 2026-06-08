@echo off
REM Double-click to sample تهذيب الكمال (book 3722) for studying its prose layout.
REM First run downloads the book (resumable — may take a few minutes); later runs are instant.
REM Read-only: it never touches data/rijal.jsonl.
cd /d "%~dp0"
echo Sampling Tahdhib al-Kamal (book 3722).
echo The FIRST run downloads the book - this can take a few minutes (rate-limited).
echo It is read-only and does NOT modify rijal.jsonl.
echo.
".venv\Scripts\python.exe" -m scripts.sample_source 3722 --entries 12 --out tahdhib_kamal.txt
echo.
echo Done. Created: tahdhib_kamal.txt
echo Please upload that file in the chat.
echo.
pause
