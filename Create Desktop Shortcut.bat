@echo off
REM ── Creates a "TISL Backup Viewer" shortcut on the Desktop and Start Menu ──
REM Double-click this once. The shortcuts launch run.bat (with its console)
REM and use icon.ico. Safe to run again — it just refreshes the shortcuts.

setlocal
set "APPDIR=%~dp0"
if "%APPDIR:~-1%"=="\" set "APPDIR=%APPDIR:~0,-1%"

set "TARGET=%APPDIR%\run.bat"
set "ICON=%APPDIR%\icon.ico"
set "NAME=TISL Backup Viewer"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "foreach ($dir in @($ws.SpecialFolders('Desktop'), (Join-Path $ws.SpecialFolders('Programs') 'TISL'))) {" ^
  "  if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }" ^
  "  $lnk = $ws.CreateShortcut((Join-Path $dir '%NAME%.lnk'));" ^
  "  $lnk.TargetPath = '%TARGET%';" ^
  "  $lnk.WorkingDirectory = '%APPDIR%';" ^
  "  $lnk.IconLocation = '%ICON%';" ^
  "  $lnk.Description = 'Open and read encrypted TISL .wnkjba backups';" ^
  "  $lnk.Save();" ^
  "}"

if %errorlevel%==0 (
  echo.
  echo   Done. Look for "%NAME%" on your Desktop and in the Start Menu.
) else (
  echo.
  echo   Could not create the shortcut automatically.
)
echo.
pause
