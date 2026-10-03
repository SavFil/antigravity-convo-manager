@echo off
title Install Antigravity Conversation Manager Plugin
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0install-plugin.ps1"
pause
