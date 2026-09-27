@echo off
REM ── TISL Backup Viewer — Windows launcher ────────────────────────────────
REM Double-click this file to start the viewer. First run sets everything up.

cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 ( set "PY=py -3" ) else ( set "PY=python" )

if not exist ".venv" (
    echo Setting up for first use...
    %PY% -m venv .venv
    call ".venv\Scripts\activate.bat"
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
) else (
    call ".venv\Scripts\activate.bat"
)

echo Starting TISL Backup Viewer...
streamlit run app.py
pause
