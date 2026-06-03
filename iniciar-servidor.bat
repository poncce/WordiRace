@echo off
cd /d "%~dp0backend"

echo Buscando servidor anterior en puerto 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000"') do (
  if not "%%a"=="0" (
    echo Cerrando proceso %%a...
    taskkill /F /PID %%a >nul 2>&1
    timeout /t 1 >nul
  )
)

echo Iniciando servidor...
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
