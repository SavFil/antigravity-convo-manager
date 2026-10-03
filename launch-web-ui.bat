@echo off
title Antigravity Conversation Manager
echo ===================================================
echo  Starting Antigravity Conversation Manager Web UI...
echo ===================================================
cd /d "%~dp0"
python server.py
pause
