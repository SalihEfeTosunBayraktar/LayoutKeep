@echo off
REM A public-domain mathematics book (Project Gutenberg #31061, 556 pages) as a held-out run.
REM Gutenberg is freely redistributable, so unlike the commercial textbook this one may be
REM published: the comparison site can carry it once the run exists.
REM
REM Short by design: 6 chunks x 4 pages keeps the run near half an hour on the local model,
REM which is enough to measure a long, formula-dense book page by page without blocking the
REM machine for an evening. Raise --limit-chunks for a longer run.
cd /d C:\MyProjects\AntigravityProjects\AI_and_LLM\LayoutKeep
set PYTHONIOENCODING=utf-8
set LAYOUTKEEP_DATA_DIR=%LOCALAPPDATA%\Temp\lk-data
.venv\Scripts\python.exe tools\audit\translate_book.py ^
  "_artifacts/heldout/sources/gutenberg_31061_history_of_mathematics.pdf" ^
  --name gutenberg_math --to tr --model google/gemma-4-e4b --workers 7 ^
  --pages-per-chunk 4 --limit-chunks 6 --layout-detector --resume ^
  --memory > "%LOCALAPPDATA%\Temp\lk_gutenberg_math.txt" 2>&1
echo exit=%ERRORLEVEL% >> "%LOCALAPPDATA%\Temp\lk_gutenberg_math.txt"
