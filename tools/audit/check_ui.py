"""Mockup 11 (çift panel önizleme) ve mockup 10 (progress) kodda var mı? + app.py akışı."""
import os
from _common import setup

setup()



# app.py'nin kalanini oku (81-119)
with open("src/layoutkeep/ui/app.py", encoding="utf-8") as f:
    print(f.read())

# progress.py'de yan yana (çift panel) önizleme var mi?
with open("src/layoutkeep/ui/progress.py", encoding="utf-8") as f:
    content = f.read()
print("progress.py length:", len(content))
for kw in ("segment_translated", "side", "dual", "panel", "preview"):
    print(f"  '{kw}' occurrences:", content.count(kw))
