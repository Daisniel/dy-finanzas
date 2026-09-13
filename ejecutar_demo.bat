@echo off
cd /d "%~dp0"
if not exist "data\demo.db" (
    echo No se encontro data\demo.db.
    echo Ejecuta scripts\create_demo_db.py para reconstruirla.
    pause
    exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
    echo No se encontro el entorno virtual .venv.
    echo Ejecuta primero instalar.bat.
    pause
    exit /b 1
)
copy /Y "data\demo.db" "data\impercontrol.db" >nul
if exist "data\impercontrol.db-wal" del /Q "data\impercontrol.db-wal"
if exist "data\impercontrol.db-shm" del /Q "data\impercontrol.db-shm"
echo Base DEMO restaurada.
".venv\Scripts\python.exe" main.py
if errorlevel 1 pause
