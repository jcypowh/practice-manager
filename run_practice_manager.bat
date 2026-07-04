@echo off
cd /d "%~dp0"
title Practice Manager Server
echo Starting Practice Manager...
start "Practice Manager Server" cmd /k python app.py
timeout /t 2 /nobreak >nul
start "" http://localhost:5003
