@echo off
setlocal
cd /d "%~dp0"
echo === ARES Companion one-time setup ===

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  echo Python was not found. Install it from python.org first, then run this again.
  pause
  exit /b 1
)

if not exist main.py (
  echo main.py is not in this folder. Put this file next to main.py, ares_companion.py and ares_sprites.py.
  pause
  exit /b 1
)

echo Installing packages...
%PY% -m pip install --upgrade PySide6 psutil requests
if errorlevel 1 (
  echo Package install failed.
  pause
  exit /b 1
)

%PY% patch_companion.py
if errorlevel 1 (
  echo Patch failed, see the message above.
  pause
  exit /b 1
)

%PY% ares_companion.py --install-startup

echo Starting Ares now...
where pythonw >nul 2>nul && (start "" pythonw ares_companion.py & goto started)
where pyw >nul 2>nul && (start "" pyw -3 ares_companion.py & goto started)
start "" %PY% ares_companion.py
:started
echo.
echo Done. Ares is on your screen and will start by himself every time you log in.
echo Press the ` key (left of 1) to make him listen. Log: %USERPROFILE%\ARES_Data\companion.log
pause
