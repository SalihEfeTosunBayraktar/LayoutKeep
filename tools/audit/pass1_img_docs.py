"""Geçiş 1 devam — image-pipeline doküman iddialarının koda karşı doğrulanması:
R1 (flat-fill vurgu kaybı), R2 (çok sütun), R3 (serif→sans), R4 (unit karışımı),
D4 (rotation yok) + vision mimari iddiaları (openai_compat content-block)."""
import os
import sys
from _common import setup

setup()




from layoutkeep.core.docir import BBox, Block, BlockRole, Direction, Line, Span, Style
from layoutkeep.ocr.inpaint import inpaint_block
from PIL import Image

# --- R1: flat-fill vurgu kaybı — inpaint_block span bazlı; vurgu rengi BEYAZ degil gerçek bg rengi
img = Image.new("RGB", (200, 60), "#ffffff")
d = ImageDraw = None
from PIL import ImageDraw
dr = ImageDraw.Draw(img)
dr.rectangle((10, 10, 190, 50), fill="#ffff00")  # sarı vurgu şeridi
dr.text((15, 20), "Hello", fill="#000000")

span_style = Style(font_family="Arial", size=12, color="#000000", background="#ffff00")
span = Span(text="Hello", bbox=BBox(10, 10, 190, 50), style=span_style, direction=Direction.LTR)
block = Block(id="img0#0", role=BlockRole.BODY, bbox=BBox(10, 10, 190, 50),
             lines=[Line(spans=[span], bbox=BBox(10, 10, 190, 50))], direction=Direction.LTR)

out = inpaint_block(img, block)
px = out.getpixel((100, 30))
print(f"R1: vurgulu span inpaint sonrasi (100,30) rengi: #{px[0]:02x}{px[1]:02x}{px[2]:02x}")
print("    -> sarı (#ffff00) ise vurgu KORUNUR (doküman 'kaybolur' diyor — yanlış iddia olabilir)")

# --- R4: _style_in_pixels fallback — heights bos ise block.bbox.height (tum blok!) kullanilir
from layoutkeep.writers.image_writer import _style_in_pixels

st = Style(font_family="Arial", size=12.0)
blk_multi = Block(id="x", role=BlockRole.BODY, bbox=BBox(0, 0, 100, 300),
                  lines=[Line(spans=[], bbox=None) for _ in range(10)], direction=Direction.LTR)
res = _style_in_pixels(st, blk_multi)
print(f"\nR4: bbox'i olmayan satirlarla _style_in_pixels -> size={res.size}")
print(f"    (10 satirli blokta beklenen ~tek satir; 300 = tum blok yuksekligi -> fit kucultur)")

# --- D4: image hattında rotation hic kullaniliyor mu?
import inspect
import layoutkeep.readers.image_reader as ir
src = inspect.getsource(ir)
print(f"\nD4: image_reader kaynak kodunda 'rotation' gecen satir: {'rotation' in src}")

# --- R3: fontmatch classify — serif kaynak 'Arial' etiketiyle sans'a mı gidiyor?
from layoutkeep.fitting.fontmatch import resolve_font
m = resolve_font("Arial", "tr")
print(f"\nR3: resolve_font('Arial','tr') -> {m.resolved_path}, quality={m.quality}")

# --- vision mimari iddiası: openai_compat content-block'u destekliyor mu?
src_oc = open("src/layoutkeep/providers/openai_compat.py", encoding="utf-8").read()
print(f"\nVision: openai_compat.py'de 'image_url' / multipart content-block kodu: {'image_url' in src_oc}")
print(f"Vision: 'content' diziye cevrilebiliyor mu: {'isinstance' in src_oc and 'list' in src_oc}")

# --- backlog P1.1/P1.2: google/azure provider dosyalari var mi?
print(f"\nBacklog: providers/google_translate.py var mi: {os.path.exists('src/layoutkeep/providers/google_translate.py')}")
print(f"Backlog: providers/azure_translate.py var mi: {os.path.exists('src/layoutkeep/providers/azure_translate.py')}")
print(f"Backlog: providers/vision.py var mi: {os.path.exists('src/layoutkeep/providers/vision.py')}")
