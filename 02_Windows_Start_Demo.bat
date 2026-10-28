@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run 01_Windows_Setup_Demo.bat before starting.
  pause
  exit /b 1
)
set "DATABASE_URL=sqlite:///./farmkart_demo.db"
set "APP_ENV=development"
set "COOKIE_SECURE=0"
echo Farmkart Foods trial starts at http://127.0.0.1:8000
 echo Only this Windows PC can access the local trial.
call .venv\Scripts\python.exe -m uvicorn farmkart_app.main:app --host 127.0.0.1 --port 8000
pause
