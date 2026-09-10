"""Tunable audit düzeltmesi: key= ile tanımlanan TÜM tunable'ların kullanım kontrolü."""
import os
from _common import setup

setup()
import re



tun_src = open("src/layoutkeep/core/tunables.py", encoding="utf-8").read()
names = re.findall(r'key="([a-z0-9_.]+)"', tun_src)
print(f"tanimli tunable: {len(names)}")

all_src = {}
for root, dirs, files in os.walk("src"):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for fn in files:
        if fn.endswith(".py"):
            p = os.path.join(root, fn)
            if p.endswith("core\\tunables.py"):
                continue
            all_src[p] = open(p, encoding="utf-8").read()

dead = []
for name in names:
    if not any(f'"{name}"' in s for s in all_src.values()):
        dead.append(name)
print(f"hiçbir yerde okunmayan tunable: {len(dead)}")
for d in dead:
    print(f"  OLU: {d}")

# UI tweaks dialog'da gorunen ama kodda okunmayanlar ayri isaret
ui_src = "\n".join(s for p, s in all_src.items() if "ui" in p)
ui_only_dead = [d for d in dead if f'"{d}"' in ui_src]
print(f"\nbunlardan UI'da ayarlanabilenler: {ui_only_dead}")
