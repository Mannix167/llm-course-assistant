@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0"

echo Starting Course Learning Agent...
echo.

if not exist "backend\app\main.py" (
  echo Backend entry not found: backend\app\main.py
  pause
  exit /b 1
)

if not exist "frontend\package.json" (
  echo Frontend entry not found: frontend\package.json
  pause
  exit /b 1
)

set "PYTHON_EXE=python"
where python >nul 2>nul
if errorlevel 1 (
  if exist "%LocalAppData%\Programs\Python\Python314\python.exe" (
    set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python314\python.exe"
  ) else (
    where py >nul 2>nul
    if errorlevel 1 (
      echo Python was not found. Please install Python or add it to PATH.
      pause
      exit /b 1
    ) else (
      set "PYTHON_EXE=py"
    )
  )
)

where npm.cmd >nul 2>nul
if errorlevel 1 (
  echo npm.cmd was not found. Please install Node.js.
  pause
  exit /b 1
)

set "BACKEND_PORT=8001"

echo Backend:  http://127.0.0.1:%BACKEND_PORT%
echo Frontend: http://127.0.0.1:5173
echo.
echo Two command windows will open. Keep them open while using the app.
echo If this is the first run, install dependencies first:
echo   backend:  pip install -r backend\requirements.txt
echo   frontend: npm install inside frontend\
echo.

start "Course Agent Backend" cmd /k "cd /d ""%~dp0backend"" && ""%PYTHON_EXE%"" -m uvicorn app.main:app --host 127.0.0.1 --port %BACKEND_PORT%"
start "Course Agent Frontend" cmd /k "cd /d ""%~dp0frontend"" && set ""VITE_API_BASE_URL=http://127.0.0.1:%BACKEND_PORT%"" && npm.cmd run dev -- --host 127.0.0.1 --port 5173"

echo Waiting for services to start...
powershell -NoProfile -Command "Start-Sleep -Seconds 6" >nul
start "" "http://127.0.0.1:5173"

echo Done. You can close this launcher window.
powershell -NoProfile -Command "Start-Sleep -Seconds 3" >nul
endlocal
