@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1" %*
if errorlevel 1 (
    echo RUPA build failed. Review the build log.
    pause
    exit /b 1
)
echo RUPA build completed.
pause
