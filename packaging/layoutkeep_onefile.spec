# PyInstaller spec for the LayoutKeep standalone single-file executable.
#
# Build from the repo root:
#     .venv\Scripts\python.exe -m PyInstaller packaging\layoutkeep_onefile.spec --noconfirm --clean
#
# Produces dist/LayoutKeep.exe (standalone single file).

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hiddenimports = [
    # Imported lazily by the CLI and the UI, so PyInstaller's static analysis misses them.
    "layoutkeep.readers.epub_reader",
    "layoutkeep.readers._epub_css",
    "layoutkeep.readers.pdf_reader",
    "layoutkeep.readers.docx_reader",
    "layoutkeep.readers.image_reader",
    "layoutkeep.writers.epub_writer",
    "layoutkeep.writers.pdf_writer",
    "layoutkeep.writers.docx_writer",
    "layoutkeep.writers.image_writer",
    "layoutkeep.writers.html_writer",
    "layoutkeep.writers.pdf_generator",
    "layoutkeep.writers.docx_generator",
    "layoutkeep.writers.epub_generator",
    "layoutkeep.writers.converter",
    "layoutkeep.ui.theme",
    "layoutkeep.ui.branding",
    "layoutkeep.ui.crashlog",
    "layoutkeep.ui.tokens",
    "layoutkeep.ui.icons",
    "layoutkeep.ui.strings",
    "layoutkeep.ui.eta",
    "layoutkeep.ui.languages",
    "layoutkeep.ui.model_catalog",
    "layoutkeep.ui.progress",
    "layoutkeep.ui.drop_zone",
    "layoutkeep.ui.header",
    "layoutkeep.ui.job_setup",
    "layoutkeep.ui.completion",
    "layoutkeep.ui.main_window",
    "layoutkeep.ui.provider_profile",
    "PySide6.QtSvg",
    "layoutkeep.providers.openai_compat",
    "layoutkeep.providers.fake",
    "layoutkeep.providers.memory",
    "layoutkeep.providers.glossary",
    "layoutkeep.providers.cached",
    "layoutkeep.core.range_helper",
    "layoutkeep.providers.protected",
    "layoutkeep.providers.passthrough",
    "layoutkeep.fitting.fit",
    "layoutkeep.fitting.pdf_pass",  # lazy-imported by ui/worker.py's _fit_pdf_pass
    "layoutkeep.fitting.fontmatch",
    "layoutkeep.fitting.measure",
]
# keyring picks its backend at runtime by importing it, which static analysis cannot see.
hiddenimports += collect_submodules("keyring.backends")

def _rapidocr_dir() -> Path:
    """Where rapidocr is installed in the environment this build runs in.

    Hard-coding `.venv/Lib/site-packages` breaks on any other layout; asking the interpreter
    that is doing the packaging cannot be wrong.
    """
    import rapidocr

    return Path(rapidocr.__file__).parent


_RAPIDOCR = _rapidocr_dir()


a = Analysis(
    ["../src/layoutkeep/ui/app.py"],
    pathex=["../src"],
    binaries=[],
    datas=[
        ("../src/layoutkeep/assets/fonts", "assets/fonts"),
        ("../src/layoutkeep/assets/layoutkeep_logo.svg", "assets"),
        # OCR weights and the config that names them. Without these the application ships the
        # code for image translation and none of the data it needs: rapidocr looks in a package
        # directory that a one-file build does not have, then goes to the network, which fails
        # outright offline. 31 MB of the executable is this.
        (str(_RAPIDOCR / "models"), "rapidocr/models"),
        (str(_RAPIDOCR / "config.yaml"), "rapidocr"),
        (str(_RAPIDOCR / "default_models.yaml"), "rapidocr"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore",
        "PySide6.QtMultimedia",
        "PySide6.QtQuick",
        "PySide6.QtQml",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "matplotlib",
        "pytest",
        # More Qt we never construct. Each is a few MB and none is imported anywhere in src/.
        "PySide6.QtNetwork",
        "PySide6.QtOpenGL",
        "PySide6.QtSql",
        "PySide6.QtTest",
        "PySide6.QtBluetooth",
        "PySide6.QtPositioning",
        "PySide6.QtSerialPort",
        "PySide6.QtWebSockets",
        "PySide6.QtDesigner",
        "PySide6.QtHelp",
        "PySide6.QtUiTools",
    ],
    cipher=block_cipher,
    noarchive=False,
)

# OpenCV ships a 30 MB ffmpeg library for video decoding. RapidOCR reads still images and
# nothing in LayoutKeep opens a video, so it is dead weight in every download. Measured: the
# whole cv2 package is 113 MB, of which this DLL is 30.
_DROP_BINARIES = ("opencv_videoio_ffmpeg",)
a.binaries = [
    entry for entry in a.binaries
    if not any(token in entry[0].lower() for token in _DROP_BINARIES)
]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="LayoutKeep",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    # The LK mark, so the file in Explorer and the button on the taskbar are ours rather than
    # PyInstaller's default. Built from docs/mockups/06_logo_app_icon_transparent.png at every
    # size Windows asks for - a single-size .ico gets scaled badly in the small ones.
    icon="layoutkeep.ico",
)
