@echo off
rem Start the CSA Portal: install anything missing, start the backend and frontend, open the browser.
rem Double-click this file, or run it from a terminal. Close the window or press Ctrl+C to stop the portal.
setlocal
cd /d "%~dp0"
title CSA Portal

set "PORTAL_URL=http://127.0.0.1:9080"

rem Already running? Just open it.
curl -s -f -o nul "%PORTAL_URL%/api/health" 2>nul
if not errorlevel 1 (
  echo The portal is already running. Opening %PORTAL_URL%
  start "" "%PORTAL_URL%"
  exit /b 0
)

where uv >nul 2>nul
if errorlevel 1 (
  echo uv is not installed. Install it from https://docs.astral.sh/uv/ and run this again.
  goto :failed
)
where npm >nul 2>nul
if errorlevel 1 (
  echo Node.js is not installed. Install it from https://nodejs.org/ and run this again.
  goto :failed
)

echo Checking Python packages...
call uv sync --quiet
if errorlevel 1 goto :failed

if not exist "node_modules\" (
  echo Installing launcher packages...
  call npm install --no-fund --no-audit
  if errorlevel 1 goto :failed
)
if not exist "frontend\node_modules\" (
  echo Installing frontend packages...
  call npm --prefix frontend install --no-fund --no-audit
  if errorlevel 1 goto :failed
)

echo Starting the portal at %PORTAL_URL% ...
call npm run dev
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo The portal did not start. See the messages above.
pause
exit /b 1
