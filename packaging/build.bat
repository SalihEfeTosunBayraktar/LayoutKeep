@echo off
REM Build the release executable, detached, with a log to poll.
REM
REM WHY THIS EXISTS: PyInstaller takes about eight minutes, and a background job tracked by the
REM agent is cut around the twenty-minute mark - a build that looks like it died. Starting it
REM detached and reading a log file is the project's own rule for anything long
REM (docs/PACKAGING.md), so the recipe lives in one place instead of being retyped every release.
REM
REM Usage:  packaging\build.bat      (from anywhere)
REM         then watch %LOCALAPPDATA%\Temp\lk_build.txt for "exit=0" and the size line.
cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8
set LOG=%LOCALAPPDATA%\Temp\lk_build.txt
.venv\Scripts\python.exe -m PyInstaller packaging\layoutkeep_onefile.spec --noconfirm --clean > "%LOG%" 2>&1
echo exit=%ERRORLEVEL% >> "%LOG%"
for %%I in (dist\LayoutKeep.exe) do echo size=%%~zI >> "%LOG%"
