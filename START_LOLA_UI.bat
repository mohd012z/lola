@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 lola_ui.py
  goto :eof
)

where python >nul 2>nul
if %errorlevel%==0 (
  python lola_ui.py
  goto :eof
)

echo.
echo Python was not found.
echo Install Python 3 and make sure "Add Python to PATH" is enabled.
echo.
pause
