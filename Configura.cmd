@echo off
cd /d "%~dp0"
set "COMP_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%COMP_PY%" (
  "%COMP_PY%" setup_env.py
) else (
  python setup_env.py
)
pause
