@echo off
REM A public-domain mathematics book (Project Gutenberg #31061, 556 pages) as a held-out run.
REM Gutenberg is freely redistributable, so unlike the commercial textbook this one may be
REM published: the comparison site can carry it once the run exists.
REM
REM Short by design: 6 chunks x 4 pages keeps the run near half an hour on the local model,
REM which is enough to measure a long, formula-dense book page by page without blocking the
REM machine for an evening. Raise --limit-chunks for a longer run.
REM Depo koku betigin yerinden bulunur / the repository root is found from this script's location.
cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8
set LAYOUTKEEP_DATA_DIR=%LOCALAPPDATA%\Temp\lk-data
REM Model LK_MODEL ile degistirilebilir / the model can be overridden with LK_MODEL.
if not defined LK_MODEL set LK_MODEL=google/gemma-4-e4b
.venv\Scripts\python.exe tools\audit\translate_book.py ^
  "_artifacts/heldout/sources/gutenberg_31061_history_of_mathematics.pdf" ^
  --to tr --model %LK_MODEL% --workers 7 ^
  --work "_artifacts/heldout/live/gutenberg_math" ^
  --out "_artifacts/heldout/live/gutenberg_math/gutenberg_math.tr.pdf" ^
  --pages-per-chunk 4 --limit-chunks 6 --layout-detector --resume ^
  > "%LOCALAPPDATA%\Temp\lk_gutenberg_math.txt" 2>&1
echo exit=%ERRORLEVEL% >> "%LOCALAPPDATA%\Temp\lk_gutenberg_math.txt"
