@echo off
setlocal
cd /d "%~dp0"
echo --------------------------------------------
echo Farmkart Foods - Local Trial Setup (ONE PC)
echo --------------------------------------------
echo This trial is NOT for live farmer billing.
where py >nul 2>nul
if %errorlevel% == 0 (set "PY=py -3") else (set "PY=python")
%PY% --version || goto failed
if not exist .venv (%PY% -m venv .venv || goto failed)
call .venv\Scripts\python.exe -m pip install --upgrade pip || goto failed
call .venv\Scripts\python.exe -m pip install -r requirements.txt || goto failed
set "DATABASE_URL=sqlite:///./farmkart_demo.db"
call .venv\Scripts\python.exe -m farmkart_app.bootstrap init || goto failed
echo.
echo Create your first staff user. Use OWNER role initially.
call .venv\Scripts\python.exe -m farmkart_app.bootstrap user || goto failed
echo Setup completed. Run 02_Windows_Start_Demo.bat
pause
exit /b 0
:failed
echo Setup failed. Please see the error messages above.
pause
exit /b 1
