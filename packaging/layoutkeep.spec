# PyInstaller spec for the LayoutKeep desktop app.
#
# Build from the repo root:
#     .venv/Scripts/python.exe -m PyInstaller packaging/layoutkeep.spec --noconfirm
#
# Produces dist/LayoutKeep/ (one folder, not one file - a single-file build unpacks to a temp
# directory on every launch, which is slow for a ~200 MB Qt app).
#
# Not signed. Windows SmartScreen will warn, and macOS will refuse without notarisation.
# Signing needs certificates the project does not have yet - see docs/PACKAGING.md.

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hiddenimports = [
    # Imported lazily by the CLI and the UI, so PyInstaller's static analysis misses them.
    "layoutkeep.readers.epub_reader",
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
    "layoutkeep.fitting.fontmatch",
    "layoutkeep.fitting.measure",
]
# keyring picks its backend at runtime by importing it, which static analysis cannot see.
hiddenimports += collect_submodules("keyring.backends")

a = Analysis(
    ["../src/layoutkeep/ui/app.py"],
    pathex=["../src"],
    binaries=[],
    # The substitute fonts ship with the app: a stock Windows install has none of them, and
    # without them font substitution silently degrades. The OFL requires the licence texts to
    # travel with the fonts, so they are bundled too.
    datas=[
        ("../src/layoutkeep/assets/fonts", "assets/fonts"),
        ("../src/layoutkeep/assets/layoutkeep_logo.svg", "assets"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Qt ships a lot we never touch. Dropping these saves roughly 80 MB.
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
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LayoutKeep",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="LayoutKeep",
)
