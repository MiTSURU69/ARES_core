@echo off
cd /d "%~dp0"
echo Close any running Ares first (tray icon -> Quit, or end pythonw.exe in Task Manager).
echo Running Ares with a visible console so errors show up here...
echo.
where python >nul 2>nul && (python ares_companion.py) || (py -3 ares_companion.py)
echo.
echo Ares stopped. Copy any error text above and send it to me.
pause
