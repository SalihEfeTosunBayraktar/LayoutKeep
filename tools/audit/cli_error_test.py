"""CLI hata yolları: (1) sunucu kapalı -> ne oluyor? (2) RuntimeError yakalanıyor mu?"""
import os
import subprocess
import sys
from _common import setup

setup()



# Sunucu yok: 127.0.0.1:9 kapatilmis port
env = dict(os.environ)
env["PYTHONPATH"] = "src"
r = subprocess.run(
    [sys.executable, "-m", "layoutkeep.cli", "translate", "_artifacts/input/sample.epub",
     "--to", "tr", "--provider", "openai", "--model", "m",
     "--base-url", "http://127.0.0.1:9/v1", "--timeout", "3"],
    capture_output=True, text=True, env=env, timeout=60,
)
print("=== STDOUT ===")
print(r.stdout)
print("=== STDERR (son 15 satir) ===")
print("\n".join(r.stderr.splitlines()[-15:]))
print("exit code:", r.returncode)
print()
print("Traceback sızıyor mu:", "Traceback" in r.stderr)
