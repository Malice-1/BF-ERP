@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Environnement Python absent. Suivez docs\DOCUMENTATION_TECHNIQUE.md.
  exit /b 1
)
".venv\Scripts\python.exe" manage.py migrate --settings=config.demo_settings
if errorlevel 1 exit /b 1
set "BF_ERP_DEMO_HOST=127.0.0.1"
if not "%~1"=="" set "BF_ERP_DEMO_HOST=%~1"
echo Ouvrez http://%BF_ERP_DEMO_HOST%:8000/connexion/
".venv\Scripts\python.exe" manage.py runserver "%BF_ERP_DEMO_HOST%:8000" --settings=config.demo_settings
