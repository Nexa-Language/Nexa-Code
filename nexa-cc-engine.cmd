@echo off
REM nexa-cc-engine — Engine launcher for Claude Code Nexa port (Windows)
REM Usage: nexa-cc-engine.cmd (spawned by ui-ink/src/engine.ts)
REM Pre-warms Python imports + runs main.py in JSON events mode
cd /d "%~dp0"
set PYTHONUNBUFFERED=1
set PYTHONIOENCODING=utf-8
set NEXA_JSON_EVENTS=1
set NEXA_PERMISSION_MODE=%1
if "%NEXA_PERMISSION_MODE%"=="" set NEXA_PERMISSION_MODE=default
python -u src/main.py
