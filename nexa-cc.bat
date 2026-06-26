@echo off
REM nexa-cc -- CLI wrapper for Claude Code Nexa port (Windows)
cd /d "%~dp0"
nexa run src/main.nx %*
