@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-real.ps1"
if errorlevel 1 pause
