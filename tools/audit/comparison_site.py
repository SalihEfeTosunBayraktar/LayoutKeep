"""Build the side-by-side comparison site: every held-out document, original against translation.

The measurement pages say what the audit found; this one lets a person look. Each document becomes
a page of the site with a draggable divider over the two renderings of the same page - the original
and what came out of the pipeline - so a reader can see for themselves whether a page kept its
layout, its figures and its meaning.

Sources come from `_artifacts/heldout/sources/`, translations from the recorded campaign runs
(`<run>/<name>.tr.pdf` when a full document was assembled, else the per-chunk `out/t_*.pdf` in
order) plus the newest live run in `_artifacts/heldout/live/`.

    python tools/audit/comparison_site.py [--out docs/comparison] [--dpi 144] [--max-pages 8]

Everything is written under the output directory: `index.html` plus `img/<document>/<page>_{a,b}.jpg`.
No network, no CDN - the file opens from disk.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "_artifacts/heldout/sources"
RUNS = ROOT / "_artifacts/heldout/runs"
LIVE = ROOT / "_artifacts/heldout/live"
RUN_SCRIPT = ROOT / "_artifacts/heldout/run_heldout.sh"


def _run_sources() -> dict[str, str]:
    """Which file each run translated, taken from the campaign's own script.

    The run names and the source file names do not match (`arxiv_19113` is
    `arxiv_2609.19113.pdf`, `cookbook_1907` is `archive_cookbook_1907.pdf`), and the mapping only
    exists in the script that launched the runs. Reading it here means a run added to the campaign
    shows up on the site without a second list to keep in step.
    """
    if not RUN_SCRIPT.exists():
        return {}
    mapping: dict[str, str] = {}
    for line in RUN_SCRIPT.read_text(encoding="utf-8").splitlines():
        match = re.match(r"(?:pdf|single|\(\s*single)\s+(\S+)\s+(\S+)\.(pdf|epub|png|jpg)", line)
        if match:
            mapping[match.group(1)] = f"{match.group(2)}.{match.group(3)}"
    return mapping


def _source_for(run: Path, mapping: dict[str, str]) -> Path | None:
    named = mapping.get(run.name)
    if named and (SOURCES / named).exists():
        return SOURCES / named
    for candidate in (SOURCES / f"{run.name}.pdf", SOURCES / f"{run.name}_full.pdf"):
        if candidate.exists():
            return candidate
    return None


@dataclass
class Document:
    """One sample: page by page, where its original is and what came out for it, plus the audit."""

    name: str
    title: str
    pairs: list[tuple[Path, int, Path, int]]  # (original pdf, page, translation pdf, page)
    losses: str = ""
    note: str = ""
    origin: str = ""
    #: Commit the run was recorded at, and a warning when it is not the commit the tree is on: a
    #: page kept from an older engine is honest evidence about *that* engine, and the site has to
    #: say so rather than let it pass for the current one.
    commit: str = ""
    stale: str = ""


def _translation_pdfs(run: Path) -> list[Path]:
    """The translated pages in order: the assembled document if there is one, else the chunks."""
    assembled = sorted(run.glob("*.tr.pdf"))
    if assembled:
        return [assembled[0]]
    return sorted(run.glob("out/t_*.pdf"))


def _sample_pages(total: int, cap: int) -> list[int]:
    """Which pages to show: the first, then evenly spread, never more than `cap`."""
    if total <= cap:
        return list(range(total))
    step = (total - 1) / (cap - 1)
    return sorted({round(i * step) for i in range(cap)})


def _head_commit() -> str:
    """The short commit the working tree is on, so a run can be dated against it.

    Read straight out of `.git` rather than through `git rev-parse`: this is a one-time label for
    the page, and a subprocess per document would cost more than it is worth. A linked worktree
    keeps its git directory elsewhere, in which case the label is simply left off.
    """
    try:
        head = (ROOT / ".git" / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if head.startswith("ref: "):
        try:
            return (ROOT / ".git" / head.removeprefix("ref: ").strip()).read_text(
                encoding="utf-8"
            ).strip()[:7]
        except OSError:
            return ""
    return head[:7]


def _run_commit(run: Path) -> str:
    written = run / "commit.txt"
    return written.read_text(encoding="utf-8").strip()[:7] if written.exists() else ""


def _loss_summary(run: Path) -> str:
    report = run / "audit.json"
    if not report.exists():
        return ""
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    counts = data.get("counts", {})
    if not counts:
        return ""
    return ", ".join(f"{kind} {value}" for kind, value in sorted(counts.items()))


def _campaign_documents() -> list[Document]:
    documents: list[Document] = []
    mapping = _run_sources()
    head = _head_commit()
    for run in sorted(RUNS.iterdir()):
        if not run.is_dir():
            continue
        if not _publishable(run):
            continue  # a source that must not be republished (see NOT_PUBLISHABLE)
        source = _source_for(run, mapping)
        if source is None or source.suffix.lower() != ".pdf":
            continue  # posters and epubs are covered by their own format's run, or not at all
        translated = _translation_pdfs(run)
        if not translated:
            continue
        with pymupdf.open(source) as original:
            original_pages = original.page_count
        pairs: list[tuple[Path, int, Path, int]] = []
        for path in translated:
            with pymupdf.open(path) as chunk:
                for index in range(chunk.page_count):
                    pairs.append((source, min(len(pairs), original_pages - 1), path, index))
        documents.append(
            Document(
                name=run.name,
                title=run.name.replace("_", " "),
                pairs=pairs,
                losses=_loss_summary(run),
                commit=_run_commit(run),
                stale=(
                    f"kayıt {_run_commit(run)} (güncel değil)" if _run_commit(run) and _run_commit(run) != head else ""
                ),
                origin=f"sources/{source.name} + runs/{run.name}",
            )
        )
    return documents


#: Runs whose pages must not leave this machine. The user handed this book over for testing and it
#: is a commercial textbook: the site publishes page images, so republishing them would infringe on
#: it. The translation stays on disk, the site simply does not show it.
NOT_PUBLISHABLE = frozenset({"ross_stats"})


def _publishable(run: Path) -> bool:
    """False for a run recorded from a source that must not be republished."""
    stem = run.name.split("_")
    return not any("_".join(stem[:index]) in NOT_PUBLISHABLE for index in range(1, len(stem) + 1))


#: A run name carries how it was produced, not which document it is: `cookbook_1907_r2` is the
#: second re-run of `cookbook_1907`, and `fresh_pdfmt_r6_2` is the third chunk of the sixth
#: revision of `fresh_pdfmt`.
_RUN_SUFFIX = re.compile(r"(?:_r\d+)?(?:_\d+)?$")


def _base_name(name: str) -> str:
    """The document a run directory belongs to, without the revision or chunk numbering."""
    return _RUN_SUFFIX.sub("", name) or name


def _live_documents(per_document: int = 12) -> list[Document]:
    """The freshest live run of each document, all of its chunks, as one entry.

    WHY THIS EXISTS: a live run is written chunk by chunk (`cookbook_1907_r2` holds chunk_0000.pdf
    and thirty-odd more), and showing one entry per chunk filled the sidebar with `cookbook_1907_0`,
    `..._1`, `..._2` - the same document four times, each looking like a separate sample. Grouping
    by the base name also lets a re-run *replace* the entry it is a re-run of, which is the whole
    point of running it again after a fix.
    """
    groups: dict[str, list[Path]] = {}
    for run in LIVE.iterdir():
        if run.is_dir() and _publishable(run):
            groups.setdefault(_base_name(run.name), []).append(run)

    head = _head_commit()
    documents: list[Document] = []
    for base, runs in sorted(groups.items()):
        newest = max(runs, key=lambda path: path.stat().st_mtime)
        sources = sorted((newest / "src").glob("chunk_*.pdf")) if (newest / "src").exists() else []
        outputs = sorted((newest / "out").glob("t_*.pdf")) if (newest / "out").exists() else []
        pairs: list[tuple[Path, int, Path, int]] = []
        for source, output in list(zip(sources, outputs, strict=False))[:per_document]:
            with pymupdf.open(output) as chunk:
                pairs.extend((source, page, output, page) for page in range(chunk.page_count))
        if not pairs:
            continue
        recorded = _run_commit(newest)
        documents.append(
            Document(
                name=base,
                title=base,
                pairs=pairs,
                note="en güncel kod, gerçek model",
                commit=recorded,
                stale=(
                    f"kayıt {recorded} (güncel değil)" if recorded and recorded != head else ""
                ),
                origin=f"live/{newest.name}",
            )
        )
    return documents


def collect(include_live: bool = True) -> list[Document]:
    """Every sample, freshest first, with a re-run standing in for the run it replaced.

    The old run is not deleted - its page images are the evidence of what that engine produced -
    but it is not shown as a separate entry either once the same document has been run again on
    current code: two entries for one document read as two samples.
    """
    live = _live_documents() if include_live else []
    fresh = {document.name for document in live}
    campaign = [document for document in _campaign_documents() if _base_name(document.name) not in fresh]
    return live + campaign


def _save(pix, stem: Path) -> str:
    """Write one page render, as WebP when Pillow is available.

    Measured on the heaviest page (arXiv, formulas and figures): 168 dpi JPEG 191 KB, 168 dpi WebP
    410 KB, 144 dpi WebP 313 KB. WebP buys the resolution that a zoom needs (text stays readable at
    200% - checked by eye), so the defaults are 144 dpi at quality 80 with 8 pages per document,
    which keeps the whole site around a third of the size a 168 dpi JPEG set would take. WebP needs
    Pillow, which the OCR extra brings; without it the JPEG path is used and the site still works.
    """
    try:
        from PIL import Image
    except ImportError:
        pix.save(stem.with_suffix(".jpg"), jpg_quality=76)
        return stem.with_suffix(".jpg").name
    Image.frombytes("RGB", (pix.width, pix.height), pix.samples).save(
        stem.with_suffix(".webp"), "WEBP", quality=80, method=4
    )
    return stem.with_suffix(".webp").name


def render(document: Document, out_dir: Path, dpi: int, cap: int) -> list[dict]:
    """Write the before/after images for one document and return its page records."""
    folder = out_dir / "img" / document.name
    folder.mkdir(parents=True, exist_ok=True)
    zoom = dpi / 72
    records: list[dict] = []
    for page_number in _sample_pages(len(document.pairs), cap):
        source_path, source_index, output_path, output_index = document.pairs[page_number]
        with pymupdf.open(source_path) as original:
            before = original[min(source_index, original.page_count - 1)].get_pixmap(
                matrix=pymupdf.Matrix(zoom, zoom)
            )
        before_name = _save(before, folder / f"{page_number:04d}_a")
        with pymupdf.open(output_path) as translated:
            after = translated[min(output_index, translated.page_count - 1)].get_pixmap(
                matrix=pymupdf.Matrix(zoom, zoom)
            )
        after_name = _save(after, folder / f"{page_number:04d}_b")
        records.append(
            {
                "page": page_number + 1,
                "before": f"img/{document.name}/{before_name}",
                "after": f"img/{document.name}/{after_name}",
            }
        )
    return records


PAGE_TEMPLATE = """<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LayoutKeep - orijinal / çeviri karşılaştırması</title>
<style>
  :root {{ color-scheme: dark; --ink:#e8eaed; --muted:#9aa0a6; --line:#2b2f36; --accent:#4c8dff;
           --warn:#e0a458; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font:15px/1.5 system-ui, "Segoe UI", sans-serif; background:#0f1115; color:var(--ink); }}
  header {{ padding:18px 22px; border-bottom:1px solid var(--line); position:sticky; top:0; background:#0f1115f2; backdrop-filter:blur(6px); z-index:5; }}
  h1 {{ font-size:18px; margin:0 0 4px; }}
  .sub {{ color:var(--muted); font-size:13px; }}
  main {{ display:grid; grid-template-columns: 260px 1fr; gap:0; min-height: calc(100vh - 74px); }}
  nav {{ border-right:1px solid var(--line); padding:12px; overflow:auto; max-height: calc(100vh - 74px); }}
  nav button {{ display:block; width:100%; text-align:left; margin:0 0 6px; padding:8px 10px; border:1px solid var(--line);
                border-radius:8px; background:#151922; color:var(--ink); cursor:pointer; font:inherit; }}
  nav button.active {{ border-color:var(--accent); background:#1b2433; }}
  nav button small {{ display:block; color:var(--muted); font-size:11px; }}
  section {{ padding:16px 20px 40px; }}
  h2 {{ font-size:16px; margin:4px 0 2px; }}
  .meta {{ color:var(--muted); font-size:13px; margin-bottom:12px; }}
  .meta.stale {{ color:var(--warn); }}
  nav button.stale {{ border-color:var(--warn); }}
  .viewport {{ overflow:auto; max-height:82vh; border:1px solid var(--line); border-radius:10px; background:#14171d; }}
  .stage {{ position:relative; width:100%; touch-action:none; cursor:ew-resize; }}
  .stage img {{ display:block; width:100%; height:auto; user-select:none; -webkit-user-drag:none; }}
  .stage .after {{ position:absolute; inset:0; }}
  .stage .before {{ position:relative; z-index:2; clip-path: inset(0 50% 0 0); }}
  .handle {{ position:absolute; top:0; bottom:0; left:50%; width:2px; background:var(--accent); z-index:3; }}
  .handle::after {{ content:""; position:absolute; top:50%; left:50%; width:34px; height:34px; margin:-17px 0 0 -17px;
                    border-radius:50%; border:2px solid var(--accent); background:#0f1115cc; }}
  .tag {{ position:absolute; top:10px; padding:3px 8px; border-radius:6px; font-size:12px; background:#0f1115cc; z-index:4; }}
  .tag.a {{ left:10px; }} .tag.b {{ right:10px; }}
  .pages {{ display:flex; flex-wrap:wrap; gap:6px; margin:12px 0 0; }}
  .pages button {{ padding:5px 9px; border-radius:6px; border:1px solid var(--line); background:#151922; color:var(--ink); cursor:pointer; font:inherit; font-size:13px; }}
  .pages button.active {{ border-color:var(--accent); background:#1b2433; }}
  .hint {{ color:var(--muted); font-size:12px; margin-top:8px; }}
  .zoom {{ display:flex; align-items:center; gap:8px; margin:10px 0 8px; }}
  .zoom button {{ min-width:34px; padding:5px 10px; border-radius:6px; border:1px solid var(--line); background:#151922;
                  color:var(--ink); cursor:pointer; font:inherit; font-size:14px; }}
  .zoom button:hover {{ border-color:var(--accent); }}
  .zoom .level {{ min-width:52px; text-align:center; color:var(--muted); font-size:13px; font-variant-numeric:tabular-nums; }}
</style>
</head>
<body>
<header>
  <h1>LayoutKeep — orijinal ve çeviri, yan yana</h1>
  <div class="sub">Ayırıcıyı sürükle (ya da ← → tuşları): solda orijinal, sağda çevrilmiş sayfa. Ctrl + tekerlek yakınlaştırır. {count} belge.</div>
</header>
<main>
  <nav id="docs"></nav>
  <section>
    <h2 id="title"></h2>
    <div class="meta" id="meta"></div>
    <div class="zoom">
      <button id="zoom-out" title="Uzaklaştır (Ctrl -)">−</button>
      <span class="level" id="zoom-level">100%</span>
      <button id="zoom-in" title="Yakınlaştır (Ctrl +)">+</button>
      <button id="zoom-fit" title="Genişliğe sığdır (0)">Sığdır</button>
      <span class="hint">Ctrl + tekerlek de yakınlaştırır; yakınlaşınca sayfa kaydırılır.</span>
    </div>
    <div class="viewport" id="viewport">
      <div class="stage" id="stage">
        <img class="before" id="before" alt="orijinal sayfa">
        <div class="after"><img id="after" alt="çevrilmiş sayfa"></div>
        <div class="tag a">orijinal</div>
        <div class="tag b">çeviri</div>
        <div class="handle" id="handle"></div>
      </div>
    </div>
    <div class="pages" id="pages"></div>
    <div class="hint">Görseller {dpi} dpi. Kaynak: _artifacts/heldout/{origin}.</div>
  </section>
</main>
<script>
const DATA = {data};

let current = 0, page = 0, dragging = false, ratio = 0.5, zoom = 1;
const $ = (id) => document.getElementById(id);

function setRatio(value) {{
  ratio = Math.min(1, Math.max(0, value));
  $("before").style.clipPath = `inset(0 ${{(1 - ratio) * 100}}% 0 0)`;
  $("handle").style.left = `${{ratio * 100}}%`;
}}

function setZoom(value) {{
  zoom = Math.min(4, Math.max(0.25, value));
  $("stage").style.width = (zoom * 100) + "%";
  $("zoom-level").textContent = Math.round(zoom * 100) + "%";
}}

function showDocument(index) {{
  current = index; page = 0;
  const doc = DATA[index];
  $("title").textContent = doc.title;
  $("meta").textContent = [doc.pages.length + " sayfa", doc.losses, doc.note, doc.stale]
    .filter(Boolean).join(" · ");
  $("meta").classList.toggle("stale", Boolean(doc.stale));
  $("pages").replaceChildren(...doc.pages.map((record, i) => {{
    const button = document.createElement("button");
    button.textContent = record.page;
    button.onclick = () => showPage(i);
    return button;
  }}));
  [...$("docs").children].forEach((child, i) => child.classList.toggle("active", i === index));
  showPage(0);
}}

function showPage(index) {{
  page = index;
  const record = DATA[current].pages[index];
  $("before").src = record.before;
  $("after").src = record.after;
  [...$("pages").children].forEach((child, i) => child.classList.toggle("active", i === index));
}}

const stage = $("stage");
const move = (event) => {{
  const box = stage.getBoundingClientRect();
  const x = (event.touches ? event.touches[0].clientX : event.clientX) - box.left;
  setRatio(x / box.width);
}};
stage.addEventListener("pointerdown", (event) => {{ dragging = true; move(event); }});
window.addEventListener("pointerup", () => {{ dragging = false; }});
window.addEventListener("pointermove", (event) => {{ if (dragging) move(event); }});
$("zoom-in").onclick = () => setZoom(zoom * 1.25);
$("zoom-out").onclick = () => setZoom(zoom / 1.25);
$("zoom-fit").onclick = () => setZoom(1);
$("viewport").addEventListener("wheel", (event) => {{
  if (!event.ctrlKey) return;  // plain wheel still scrolls the page
  event.preventDefault();
  setZoom(zoom * (event.deltaY < 0 ? 1.15 : 1 / 1.15));
}}, {{ passive: false }});
window.addEventListener("keydown", (event) => {{
  if (event.key === "ArrowLeft") showPage(Math.max(0, page - 1));
  if (event.key === "ArrowRight") showPage(Math.min(DATA[current].pages.length - 1, page + 1));
  if (event.key === "+" || event.key === "=") setZoom(zoom * 1.25);
  if (event.key === "-" || event.key === "_") setZoom(zoom / 1.25);
  if (event.key === "0") setZoom(1);
}});

const nav = $("docs");
DATA.forEach((doc, index) => {{
  const button = document.createElement("button");
  button.innerHTML = `${{doc.title}}<small>${{doc.pages.length}} sayfa${{doc.stale ? " · eski kayıt" : ""}}</small>`;
  button.classList.toggle("stale", Boolean(doc.stale));
  button.onclick = () => showDocument(index);
  nav.append(button);
}});
setRatio(0.5);
showDocument(0);
</script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "docs/comparison")
    parser.add_argument("--dpi", type=int, default=144)
    parser.add_argument("--max-pages", type=int, default=8)
    parser.add_argument("--no-live", action="store_true")
    args = parser.parse_args()

    documents = collect(include_live=not args.no_live)
    if not documents:
        print("no documents found under _artifacts/heldout", file=sys.stderr)
        return 1

    site: list[dict] = []
    for document in documents:
        pages = render(document, args.out, args.dpi, args.max_pages)
        print(f"{document.name:32} {len(pages):3} sayfa")
        site.append(
            {
                "title": document.title,
                "losses": document.losses,
                "note": document.note,
                "stale": document.stale,
                "pages": pages,
            }
        )

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "index.html").write_text(
        PAGE_TEMPLATE.format(
            data=json.dumps(site, ensure_ascii=False),
            count=len(site),
            dpi=args.dpi,
            origin="sources + runs + live",
        ),
        encoding="utf-8",
    )
    images = sum(1 for pattern in ("*.webp", "*.jpg") for _ in (args.out / "img").rglob(pattern))
    print(f"\n{len(site)} belge, {images} görsel -> {args.out / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
