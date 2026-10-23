@echo off
setlocal
cd /d "%~dp0.."
set "PYTHONUTF8=1"
set "ROOT=%CD%"
set "DEMO_VENV=%ROOT%\.venv-demo"

if not exist "%DEMO_VENV%\Scripts\python.exe" (
    echo Creating an isolated RUPA Demo environment...
    python -m venv "%DEMO_VENV%"
    if errorlevel 1 goto :install_failed
)

"%DEMO_VENV%\Scripts\python.exe" -m pip install -e ".[demo,research]"
if errorlevel 1 (
    goto :install_failed
)

echo Starting RUPA Local Demo...
echo Keep this window open while using the Demo.
echo Browser address: http://127.0.0.1:8501
"%DEMO_VENV%\Scripts\python.exe" -m streamlit run "demo\app.py" --server.address 127.0.0.1 --server.port 8501 --server.headless false --browser.gatherUsageStats false
if errorlevel 1 (
    echo.
    echo RUPA Demo stopped because of an error. Keep this window open and check the message above.
    pause
)
goto :end

:install_failed
echo.
echo RUPA Demo installation failed. Check Python 3.9-3.11 and the network connection, then run this file again.
pause

:end
endlocal
