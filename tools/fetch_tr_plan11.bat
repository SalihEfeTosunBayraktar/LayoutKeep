@echo off
REM Hedef klasor depo kokune gore bulunur / the target folder is resolved from the repository root.
set DEST=%~dp0..\_artifacts\heldout\sources\tr
if not exist "%DEST%" mkdir "%DEST%"
cd /d "%DEST%"
curl -sL --max-time 900 -o kalkinma_plani_11.pdf "https://www.sbb.gov.tr/wp-content/uploads/2022/07/On_Birinci_Kalkinma_Plani-2019-2023.pdf"
echo plan11 exit=%ERRORLEVEL%
