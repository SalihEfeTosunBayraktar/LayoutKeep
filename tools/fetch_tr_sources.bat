@echo off
REM Turkish source documents for the TR -> EN direction.
REM mevzuat.gov.tr is unreachable from this machine (connection times out); the Ministry of Family
REM and Social Services mirrors the same law texts, and sbb.gov.tr serves the development plan.
REM Turkish laws carry no copyright (FSEK art. 31); the plan is a state publication.
cd /d C:\MyProjects\AntigravityProjects\AI_and_LLM\LayoutKeep\_artifacts\heldout\sources\tr
echo === indirme basladi %DATE% %TIME% ===
curl -sL --max-time 600 -o tck_5237.pdf "https://www.aile.tr/uploads/chgm/uploads/pages/kanunlar/5237-sayili-turk-ceza-kanunu.pdf"
echo tck exit=%ERRORLEVEL%
curl -sL --max-time 600 -o tmk_4721.pdf "https://www.aile.tr/uploads/chgm/uploads/pages/kanunlar/4721-sayili-turk-medeni-kanunu.pdf"
echo tmk exit=%ERRORLEVEL%
curl -sL --max-time 600 -o cmk_5271.pdf "https://www.aile.tr/uploads/chgm/uploads/pages/kanunlar/5271-sayili-ceza-muhakemesi-kanunu.pdf"
echo cmk exit=%ERRORLEVEL%
curl -sL --max-time 600 -o shk_2828.pdf "https://www.aile.tr/uploads/chgm/uploads/pages/kanunlar/2828-sayili-sosyal-hizmetler-kanunu.pdf"
echo shk exit=%ERRORLEVEL%
curl -sL --max-time 900 -o kalkinma_plani_12.pdf "https://www.sbb.gov.tr/wp-content/uploads/2023/12/On-Ikinci-Kalkinma-Plani_2024-2028_11122023.pdf"
echo plan exit=%ERRORLEVEL%
dir /b *.pdf
echo === bitti %TIME% ===
