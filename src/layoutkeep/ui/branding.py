"""Brand asset loading: render the LayoutKeep logo SVG into a QPixmap.

Marka varlığı yükleme: `layoutkeep_logo.svg` dosyasını QPixmap olarak açar. Hem geliştirme
kök dizininden hem paketlenmiş EXE'nin `_MEIPASS` klasöründen bulur.

The logo SVG lives under `src/layoutkeep/assets/` so PyInstaller bundles it; the loader
searches, in order, the packaged resource dir, then the dev repo src dir.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from layoutkeep import assets

#: Baseline size the header logo is rendered at (SVG is square).
LOGO_SIZE = 36


def _candidate_paths() -> list[Path]:
    #: _MEIPASS (PyInstaller) then the dev assets dir, deduped.
    #: The spec places the SVG at <_MEIPASS>/assets/ (datas=("...svg", "assets")).
    paths: list[Path] = []
    import sys

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        paths.append(Path(meipass) / "assets" / "layoutkeep_logo.svg")
        paths.append(Path(meipass) / "layoutkeep" / "assets" / "layoutkeep_logo.svg")
    paths.append(assets.LOGO_SVG_PATH)
    return paths


def logo_pixmap(size: int = LOGO_SIZE) -> QPixmap:
    """Return the logo rendered at `size`x`size`, or an empty pixmap if the file is missing."""
    for path in _candidate_paths():
        if path.exists():
            return _render(path, size)
    return QPixmap()


def _render(path: Path, size: int) -> QPixmap:
    svg = path.read_bytes()
    renderer = QSvgRenderer(QByteArray(svg))
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(Qt.transparent)
    if renderer.isValid():
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
    return pixmap


#: Sizes Windows asks an application icon for - title bar, taskbar, alt-tab, Explorer.
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def app_icon() -> QIcon:
    """The logo as a window icon, rendered at each size rather than scaled from one.

    A single pixmap scaled down to 16px turns the mark to mush in the title bar, which is
    where it is seen most.
    """
    icon = QIcon()
    for size in ICON_SIZES:
        pixmap = logo_pixmap(size)
        if not pixmap.isNull():
            icon.addPixmap(pixmap)
    return icon
