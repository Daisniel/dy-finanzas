@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    set PYTHON_CMD=py
) else (
    set PYTHON_CMD=python
)
if not exist ".venv\Scripts\python.exe" (
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto error
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto error
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error
echo.
echo Instalacion completada. Puedes ejecutar iniciar.bat.
pause
exit /b 0
:error
echo.
echo Ocurrio un error durante la instalacion. Revisa que Python este instalado.
pause
exit /b 1
