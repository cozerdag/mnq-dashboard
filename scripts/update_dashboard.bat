@echo off
REM ─────────────────────────────────────────────────────────────
REM update_dashboard.bat
REM Writes a per-day JS file for each date in the trade log,
REM then merges ALL day files into trades.js so the dashboard
REM always has the full history regardless of which machine ran last.
REM
REM Run manually or via Task Scheduler
REM ─────────────────────────────────────────────────────────────

SET SOURCE=C:\Users\HP\mnq-bot\logs\mnq_trades_log.csv
SET DASHBOARD_DIR=C:\Users\HP\mnq-bot\dashboard
SET DEST_DATA_DIR=%DASHBOARD_DIR%\data
SET DEST_CSV=%DEST_DATA_DIR%\mnq_trades.csv
SET DEST_JS=%DEST_DATA_DIR%\trades.js
SET CONVERT=C:\Users\HP\mnq-bot\scripts\convert_trades.py
SET LOG=C:\Users\HP\mnq-bot\logs\dashboard_update.log
SET PYTHON=C:\Users\HP\anaconda3\python.exe

if not exist "%DEST_DATA_DIR%" mkdir "%DEST_DATA_DIR%"

echo [%date% %time%] Dashboard update started >> "%LOG%"

if not exist "%SOURCE%" (
    echo [ERROR] Source not found: %SOURCE%
    echo [ERROR] Source not found: %SOURCE% >> "%LOG%"
    exit /b 1
)

copy /Y "%SOURCE%" "%DEST_CSV%" > nul
echo [OK] Copied CSV >> "%LOG%"

REM Pull latest from GitHub first (picks up Mac day files)
cd /d "%DASHBOARD_DIR%"
git pull --rebase --autostash
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Git pull failed - proceeding with local data
    echo [WARNING] Git pull failed >> "%LOG%"
)

REM Write per-day files + merge into trades.js
"%PYTHON%" "%CONVERT%" "%DEST_CSV%" "%DEST_JS%"

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python conversion failed
    echo [ERROR] Python conversion failed >> "%LOG%"
    exit /b 1
)

echo [OK] trades.js generated >> "%LOG%"

REM Git commit and push
git add data\
git commit -m "Dashboard update %date% %time:~0,5%"
if %ERRORLEVEL% equ 0 (
    git push
    if %ERRORLEVEL% equ 0 (
        echo [OK] Dashboard updated and pushed to GitHub
        echo View at: https://cozerdag.github.io/mnq-dashboard
    ) else (
        echo [WARNING] Committed locally but push failed - run 'git push' manually
    )
) else (
    echo [OK] No new changes to commit
)

echo [%date% %time%] Dashboard update complete >> "%LOG%"
echo    Open: %DASHBOARD_DIR%\index.html
