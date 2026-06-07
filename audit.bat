@echo off
REM Double-click to (re)build the isnad audit report — the «التدقيق» review tab.
REM Scans every chain and lists the likely narrator-grading errors to verify by hand.
cd /d "%~dp0"
echo Tip: close the app window first, so the data files aren't locked.
echo Building the isnad audit report — this can take a few minutes on the full rijal...
echo.
".venv\Scripts\python.exe" -m scripts.audit_isnad
echo.
pause
