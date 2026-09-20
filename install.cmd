@echo off
REM Windows: install Perturbation (see perturbation\install).
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py -3 -m perturbation.install %*) else (python -m perturbation.install %*)
