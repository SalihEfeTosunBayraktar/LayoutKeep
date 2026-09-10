"""Geçiş 3 devam: page_range uçları (worker), image→image, skip+limit, DeepL hata yolu, .lkproj çıktı okuma."""
import os
import subprocess
import sys
from _common import TMP, setup

setup()


env = {**os.environ, "PYTHONPATH": "src"}
PY = sys.executable


sys.path.insert(0, "src")
from layoutkeep.core.range_helper import parse_page_range

print("=== 2) parse_page_range uçları ===")
for expr in ["0", "-1", "99", "5-2", "1-99999", "abc", ""]:
    try:
        out = parse_page_range(expr, 5)
        print(f"  {expr!r:>12} -> {out}")
    except Exception as e:
        print(f"  {expr!r:>12} -> {type(e).__name__}: {e}")

print("\n=== 3) image->image (PNG girdi, PNG cikti) ===")
r = subprocess.run(
    [PY, "-m", "layoutkeep.cli", "translate", "tests/fixtures/img_plain_white.png",
     "--to", "tr", "--provider", "fake", "-o", os.path.join(TMP, "img.tr.png")],
    capture_output=True, text=True, env=env, timeout=300,
)
print("stdout:", (r.stdout.strip().splitlines() or ["(bos)"])[-1])
print("stderr son:", (r.stderr.strip().splitlines() or ["(bos)"])[-1])
print("exit:", r.returncode)

print("\n=== 4) skip+limit birlikte ===")
r = subprocess.run(
    [PY, "-m", "layoutkeep.cli", "translate", "_artifacts/input/sample.epub",
     "--to", "tr", "--provider", "fake", "--skip", "2", "--limit", "3",
     "-o", os.path.join(TMP, "skip-limit.epub")],
    capture_output=True, text=True, env=env, timeout=120,
)
skip_lines = [ln for ln in r.stdout.splitlines() if "skip" in ln or "limit" in ln or "segments" in ln]
print("\n".join("  " + ln for ln in skip_lines))
print("exit:", r.returncode)

print("\n=== 5) DeepL gecersiz anahtar (hata mesaji) — 403 beklenir, internet gerektirmez ===")
r = subprocess.run(
    [PY, "-m", "layoutkeep.cli", "translate", "_artifacts/input/sample.epub",
     "--to", "tr", "--provider", "deepl", "--api-key", "bogus:fx",
     "-o", os.path.join(TMP, "deepl.epub")],
    capture_output=True, text=True, env=env, timeout=90,
)
print("  stdout son:", (r.stdout.strip().splitlines() or ["(bos)"])[-1])
err_last = (r.stderr.strip().splitlines() or ["(bos)"])[-1]
print("  stderr son:", err_last[:200])
print("  traceback sizdi mi:", "Traceback" in r.stderr)
print("  exit:", r.returncode)
