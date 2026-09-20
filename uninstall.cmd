@echo off
REM Windows: remove Perturbation.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py -3 -m perturbation.install uninstall) else (python -m perturbation.install uninstall)
