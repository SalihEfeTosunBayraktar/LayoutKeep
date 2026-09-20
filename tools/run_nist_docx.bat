@echo off
REM NIST DOCX test kaynagini canli kosuyla cevirir (kamu mali kaynak, yayina uygun).
REM Model mesgulken calistirmayin: LM Studio tek model yukler, istekler sirayla gider.
cd /d C:\MyProjects\AntigravityProjects\AI_and_LLM\LayoutKeep
set PYTHONIOENCODING=utf-8
set LAYOUTKEEP_DATA_DIR=%LOCALAPPDATA%\Temp\lk-data

set SRC=_artifacts\heldout\sources\nist_jres_head4.docx
set OUTDIR=_artifacts\heldout\live\nist_docx

echo === nist_docx basliyor %DATE% %TIME% ===
.venv\Scripts\python.exe -m layoutkeep translate "%SRC%" --to tr --out "%OUTDIR%\nist_docx.tr.docx" --work "%OUTDIR%\out" --provider local --target-lang tr > "%OUTDIR%\run.log" 2>&1
echo translate exit=%ERRORLEVEL% >> "%OUTDIR%\run.log"
.venv\Scripts\python.exe tools\audit\lossless_audit.py "%OUTDIR%\out" > "%OUTDIR%\audit.txt" 2>&1
echo audit exit=%ERRORLEVEL% >> "%OUTDIR%\audit.txt"
echo === bitti %DATE% %TIME% ===
