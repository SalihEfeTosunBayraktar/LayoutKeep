"""LayoutKeep bundled assets.

Paketlenmiş kaynak varlıkları. `LOGO_SVG_PATH`, uygulama logosunun SVG kaynağını gösterir.
"""

from __future__ import annotations

from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent
LOGO_SVG_PATH = ASSETS_DIR / "layoutkeep_logo.svg"
