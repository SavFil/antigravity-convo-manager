@echo off
echo Building Antigravity Conversation Manager standalone executable...
pyinstaller AntigravityConvoManager.spec --distpath dist --noconfirm
echo.
echo ========================================================
echo Build complete! Executable is located at:
echo dist\AntigravityConvoManager.exe
echo ========================================================
pause
