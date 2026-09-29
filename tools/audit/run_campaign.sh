#!/usr/bin/env bash
# Translate each campaign book with the model path, then audit it. One book at a time, so every
# book gets the server's full parallelism and a failure in one is visible before the next starts.
#
#   bash tools/audit/run_campaign.sh name=path.pdf [name=path.pdf ...]
set -u
PY=.venv/Scripts/python.exe
ROOT=_artifacts/campaign/runs
for item in "$@"; do
  name="${item%%=*}"; src="${item#*=}"
  work="$ROOT/$name"; mkdir -p "$work"
  echo "[$(date '+%F %T')] START $name ($src)" | tee -a "$ROOT/campaign.log"
  $PY tools/audit/translate_book.py "$src" --out "$work/$name.tr.pdf" --work "$work" \
      --model google/gemma-4-e4b --workers 7 --pages-per-chunk 1 --layout-detector --resume \
      > "$work/run.log" 2>&1
  tail -n 1 "$work/run.log" | tee -a "$ROOT/campaign.log"
  $PY tools/audit/lossless_audit.py --work "$work" --json "$work/audit.json" 2>&1 \
      | grep -Ev "RapidOCR|INFO" > "$work/audit.txt"
  grep -E "^L|^D1|LOSSLESS|chunks" "$work/audit.txt" | tee -a "$ROOT/campaign.log"
  echo "[$(date '+%F %T')] END $name" | tee -a "$ROOT/campaign.log"
done
