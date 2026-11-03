@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Environnement Python absent. Suivez docs\RECETTE_ACHATS.md.
  exit /b 1
)
".venv\Scripts\python.exe" manage.py migrate --settings=config.demo_settings
if errorlevel 1 exit /b 1
echo Ouvrez http://127.0.0.1:8000/connexion/
".venv\Scripts\python.exe" manage.py runserver --settings=config.demo_settings
