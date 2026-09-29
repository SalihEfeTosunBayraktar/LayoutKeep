@echo off
REM TR -> EN campaign: five Turkish documents (all >= 60 pages) plus the reverse direction (EN -> TR).
REM Turkish laws carry no copyright (FSEK art. 31); the SBB development plans are state publications,
REM so the whole set is publishable on the comparison site.
REM Runs are sequential on purpose: the model server has one queue, and two jobs at once make both slow.
REM Every run is resumable (-resume): relaunching this file picks up at the first chunk not yet written.
cd /d C:\MyProjects\AntigravityProjects\AI_and_LLM\LayoutKeep
set PYTHONIOENCODING=utf-8
set LOG=%LOCALAPPDATA%\Temp\lk_tr_campaign.txt
set PY=.venv\Scripts\python.exe
set TB=tools\audit\translate_book.py
set SRC=_artifacts\heldout\sources
set LIVE=_artifacts\heldout\live
set MODEL=google/gemma-4-e4b

echo === TR-EN campaign started %DATE% %TIME% === > "%LOG%"

REM --- smoke: two chunks, to prove the new direction end to end before committing hours ---
%PY% %TB% "%SRC%\tr\tck_5237.pdf" --from tr --to en --work "%LIVE%\tr_tck_smoke" --out "%LIVE%\tr_tck_smoke\tr_tck_smoke.en.pdf" --model %MODEL% --workers 7 --pages-per-chunk 4 --layout-detector --limit-chunks 2 >> "%LOG%" 2>&1
set SMOKE=%ERRORLEVEL%
echo smoke exit=%SMOKE% >> "%LOG%"
if not "%SMOKE%"=="0" goto fail

REM --- 1/5 Turk Ceza Kanunu, 88 pages ---
%PY% %TB% "%SRC%\tr\tck_5237.pdf" --from tr --to en --work "%LIVE%\tr_tck_5237" --out "%LIVE%\tr_tck_5237\tr_tck_5237.en.pdf" --model %MODEL% --workers 7 --pages-per-chunk 4 --layout-detector --resume >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo tr_tck_5237 exit=%RC% >> "%LOG%"

REM --- 2/5 Ceza Muhakemesi Kanunu, 91 pages ---
%PY% %TB% "%SRC%\tr\cmk_5271.pdf" --from tr --to en --work "%LIVE%\tr_cmk_5271" --out "%LIVE%\tr_cmk_5271\tr_cmk_5271.en.pdf" --model %MODEL% --workers 7 --pages-per-chunk 4 --layout-detector --resume >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo tr_cmk_5271 exit=%RC% >> "%LOG%"

REM --- 3/5 Turk Medeni Kanunu, 162 pages ---
%PY% %TB% "%SRC%\tr\tmk_4721.pdf" --from tr --to en --work "%LIVE%\tr_tmk_4721" --out "%LIVE%\tr_tmk_4721\tr_tmk_4721.en.pdf" --model %MODEL% --workers 7 --pages-per-chunk 4 --layout-detector --resume >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo tr_tmk_4721 exit=%RC% >> "%LOG%"

REM --- reverse direction: the English edition of the same plan, 263 pages, EN -> TR ---
%PY% %TB% "%SRC%\sbb_development_plan_12_en.pdf" --from en --to tr --work "%LIVE%\en_sbb_plan_12" --out "%LIVE%\en_sbb_plan_12\en_sbb_plan_12.tr.pdf" --model %MODEL% --workers 7 --pages-per-chunk 4 --layout-detector --resume >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo en_sbb_plan_12 exit=%RC% >> "%LOG%"

REM --- 4/5 On Ikinci Kalkinma Plani, 253 pages ---
%PY% %TB% "%SRC%\tr\kalkinma_plani_12.pdf" --from tr --to en --work "%LIVE%\tr_plan_12" --out "%LIVE%\tr_plan_12\tr_plan_12.en.pdf" --model %MODEL% --workers 7 --pages-per-chunk 4 --layout-detector --resume >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo tr_plan_12 exit=%RC% >> "%LOG%"

REM --- 5/5 On Birinci Kalkinma Plani, 198 pages ---
%PY% %TB% "%SRC%\tr\kalkinma_plani_11.pdf" --from tr --to en --work "%LIVE%\tr_plan_11" --out "%LIVE%\tr_plan_11\tr_plan_11.en.pdf" --model %MODEL% --workers 7 --pages-per-chunk 4 --layout-detector --resume >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo tr_plan_11 exit=%RC% >> "%LOG%"

echo === TR-EN campaign finished %TIME% === >> "%LOG%"
exit /b 0

:fail
echo === smoke failed, campaign aborted %TIME% === >> "%LOG%"
exit /b 1
