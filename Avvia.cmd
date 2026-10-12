@echo off
cd /d "%~dp0"
set "COMP_PYW=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
if exist "%~dp0.venv\Scripts\pythonw.exe" (
  start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0launch.py"
) else if exist "%COMP_PYW%" (
  start "" "%COMP_PYW%" "%~dp0launch.py"
) else (
  python launch.py
  pause
)
