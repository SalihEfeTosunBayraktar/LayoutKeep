@echo off
REM Hedef klasor depo kokune gore bulunur / the target folder is resolved from the repository root.
set DEST=%~dp0..\_artifacts\heldout\sources
if not exist "%DEST%" mkdir "%DEST%"
cd /d "%DEST%"
curl -sL --max-time 900 -o sbb_development_plan_12_en.pdf "https://www.sbb.gov.tr/wp-content/uploads/2025/03/Twelfth-Development-Plan_2024-2028.pdf"
echo en_plan exit=%ERRORLEVEL%
