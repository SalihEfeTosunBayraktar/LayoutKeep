"""Produce inspectable demo artefacts: real input files, real translated output, and a
side-by-side text dump so the result can be read without unzipping anything.

Dev tooling, not part of the shipped product. Run it from the repo root:

    .venv/Scripts/python.exe tools/make_demo.py
    .venv/Scripts/python.exe tools/make_demo.py --provider openai --model <id>

Everything lands under _artifacts/ (git-ignored).
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "_artifacts"
INPUT_DIR = ARTIFACTS / "input"
OUTPUT_DIR = ARTIFACTS / "output"

sys.path.insert(0, str(ROOT / "tests" / "fixtures"))


def _prepare_input() -> Path:
    """Build the sample EPUB. It is generated from code so it is reproducible and licence-free."""
    import build_epub_fixture

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = INPUT_DIR / "sample.epub"
    build_epub_fixture.build_sample_epub(path)
    return path


def _dump_zip(path: Path, out_dir: Path) -> None:
    """Unpack an EPUB so its XHTML can be opened in any editor."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as z:
        z.extractall(out_dir)


def _side_by_side(src: Path, out: Path, report: Path) -> None:
    """Write a per-entry comparison of the two EPUBs, with the changed XHTML shown in full."""
    a, b = zipfile.ZipFile(src), zipfile.ZipFile(out)
    names_a = [i.filename for i in a.infolist()]
    names_b = [i.filename for i in b.infolist()]
    lines: list[str] = []
    add = lines.append

    add(f"input   {src}")
    add(f"output  {out}")
    add("")
    add(f"zip entries      {len(names_a)} -> {len(names_b)}")
    add(f"same order       {names_a == names_b}")
    first = b.infolist()[0]
    add(f"first entry      {first.filename} (stored uncompressed: {first.compress_type == 0})")
    add("")
    add("per-entry comparison")
    changed: list[str] = []
    for name in names_a:
        if name not in names_b:
            add(f"  {name:32} MISSING FROM OUTPUT")
            continue
        x, y = a.read(name), b.read(name)
        if x == y:
            add(f"  {name:32} identical ({len(x)} bytes)")
        else:
            add(f"  {name:32} changed   ({len(x)} -> {len(y)} bytes)")
            changed.append(name)

    for name in changed:
        if not name.endswith((".xhtml", ".html", ".opf", ".ncx")):
            continue
        add("")
        add("=" * 78)
        add(f"{name}  --  BEFORE")
        add("=" * 78)
        add(a.read(name).decode("utf-8", "replace"))
        add("=" * 78)
        add(f"{name}  --  AFTER")
        add("=" * 78)
        add(b.read(name).decode("utf-8", "replace"))

    report.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["fake", "openai"], default="fake")
    parser.add_argument("--base-url", default="http://localhost:1234/v1")
    parser.add_argument("--model", default=None)
    parser.add_argument("--to", dest="to_lang", default="tr")
    parser.add_argument("--from", dest="from_lang", default="en")
    args = parser.parse_args(argv)

    from layoutkeep.cli import main as cli_main

    src = _prepare_input()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"sample.{args.to_lang}.epub"

    argv_translate = [
        "translate", str(src),
        "--to", args.to_lang,
        "--from", args.from_lang,
        "--provider", args.provider,
        "-o", str(out),
        "--memory", str(ARTIFACTS / "memory.sqlite"),
        "--save-project", str(OUTPUT_DIR / "sample.lkproj"),
    ]
    if args.provider == "openai":
        argv_translate += ["--base-url", args.base_url]
        if args.model:
            argv_translate += ["--model", args.model]

    print("=" * 78)
    print("TRANSLATE")
    print("=" * 78)
    rc = cli_main(argv_translate)
    if rc != 0:
        print("\ntranslation failed - not writing comparison artefacts")
        return rc

    _dump_zip(src, ARTIFACTS / "unpacked" / "input")
    _dump_zip(out, ARTIFACTS / "unpacked" / "output")
    report = OUTPUT_DIR / "comparison.txt"
    _side_by_side(src, out, report)

    print()
    print("=" * 78)
    print("ARTEFACTS")
    print("=" * 78)
    for label, path in [
        ("input epub", src),
        ("output epub", out),
        ("comparison", report),
        ("project file", OUTPUT_DIR / "sample.lkproj"),
        ("unpacked input", ARTIFACTS / "unpacked" / "input"),
        ("unpacked output", ARTIFACTS / "unpacked" / "output"),
    ]:
        print(f"  {label:16} {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
