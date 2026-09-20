"""Publish a Markdown document as a standalone page for GitHub Pages.

WHY THIS EXISTS: the project's story lives in Markdown (`docs/STORY.md`) because that is what a
repository reads well in, and it is published as a page under the Pages site because that is where
a reader arriving from the front page expects to find it. The conversion is deliberately a small
subset - headings, paragraphs, lists, tables, images, links, code, quotes - because a document
this project owns should not depend on a Markdown library's version to render.

The subset is the one `docs/STORY.md` uses; anything outside it is left as text rather than
silently dropped, so a mistake shows up in the page instead of vanishing from it.
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The page's own styling: light and dark, no external requests, no framework.
TEMPLATE = """<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<style>
  :root {{
    --bg: #ffffff; --text: #1a1f27; --muted: #5b6675; --border: #e3e8ee;
    --accent: #1d6fd6; --code-bg: #f5f7fa; --card: #f8fafc;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #14161b; --text: #e8ecf1; --muted: #98a2b3; --border: #2a3038;
      --accent: #4c9aff; --code-bg: #1c2028; --card: #1a1e25;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--text);
         font: 16.5px/1.7 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }}
  main {{ max-width: 54rem; margin: 0 auto; padding: 3.5rem 1.25rem 5rem; }}
  h1 {{ font-size: clamp(1.8rem, 4.5vw, 2.6rem); line-height: 1.15; letter-spacing: -.02em; margin: 0 0 1rem; }}
  h2 {{ font-size: 1.45rem; margin: 2.6rem 0 .8rem; padding-top: 1.2rem; border-top: 1px solid var(--border); }}
  h3 {{ font-size: 1.12rem; margin: 1.8rem 0 .5rem; }}
  h4 {{ font-size: 1rem; margin: 1.4rem 0 .4rem; }}
  p, li {{ color: var(--text); }}
  a {{ color: var(--accent); }}
  img {{ max-width: 100%; height: auto; border: 1px solid var(--border); border-radius: 10px; display: block; margin: 1.2rem 0; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1.2rem 0; font-size: .95rem; display: block; overflow-x: auto; }}
  th, td {{ border: 1px solid var(--border); padding: .5rem .65rem; text-align: left; vertical-align: top; }}
  th {{ background: var(--card); }}
  code {{ background: var(--code-bg); border: 1px solid var(--border); border-radius: 5px; padding: .08rem .3rem; font-size: .9em; }}
  pre {{ background: var(--code-bg); border: 1px solid var(--border); border-radius: 10px; padding: .9rem 1rem; overflow-x: auto; }}
  pre code {{ background: none; border: none; padding: 0; }}
  blockquote {{ margin: 1.2rem 0; padding: .6rem 1rem; border-left: 3px solid var(--accent);
                background: var(--card); border-radius: 0 8px 8px 0; color: var(--muted); }}
  hr {{ border: none; border-top: 1px solid var(--border); margin: 2.5rem 0; }}
  em {{ color: var(--muted); }}
  .home {{ display: inline-block; margin-bottom: 1.5rem; font-size: .92rem; }}
  .story-nav {{ display: flex; flex-wrap: wrap; gap: .45rem; align-items: center;
                margin: 0 0 2rem; padding: .55rem .7rem; border: 1px solid var(--border);
                border-radius: 10px; background: var(--card); font-size: .9rem; }}
  .story-nav a {{ text-decoration: none; padding: .1rem .35rem; }}
  .story-nav .here {{ background: var(--accent); color: #fff; border-radius: 6px;
                      padding: .1rem .45rem; font-weight: 600; }}
  .pager {{ display: flex; justify-content: space-between; gap: 1rem; margin: 3rem 0 0;
            padding-top: 1.2rem; border-top: 1px solid var(--border); font-size: .95rem; }}
  footer {{ margin-top: 3rem; padding-top: 1.2rem; border-top: 1px solid var(--border); color: var(--muted); font-size: .9rem; }}
</style>
</head>
<body>
<main>
<a class="home" href="../">← LayoutKeep</a>
{body}
<footer>
  Bu sayfa <code>docs/STORY.md</code> dosyasından <code>tools/story_site.py</code> ile üretildi.
  Karşılaştırma sitesi: <a href="../comparison/">orijinal ↔ çeviri</a>.
</footer>
</main>
</body>
</html>
"""


def _inline(text: str) -> str:
    """Bold, italic, code, links and images - in that order, escaping first."""
    text = html.escape(text, quote=False)
    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", r'<img alt="\1" src="\2">', text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    return re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", text)


def _table(rows: list[str]) -> str:
    """A pipe table: the second row is the alignment separator and is dropped."""
    cells = [[cell.strip() for cell in row.strip().strip("|").split("|")] for row in rows]
    header, body = cells[0], cells[2:]
    out = ["<table>", "<thead><tr>"]
    out += [f"<th>{_inline(cell)}</th>" for cell in header]
    out += ["</tr></thead>", "<tbody>"]
    for row in body:
        out.append("<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in row) + "</tr>")
    out += ["</tbody>", "</table>"]
    return "\n".join(out)


def markdown_to_html(markdown: str) -> str:
    """Convert the subset of Markdown this project's story uses."""
    lines = markdown.splitlines()
    out: list[str] = []
    paragraph: list[str] = []
    index = 0

    def flush() -> None:
        if paragraph:
            out.append("<p>" + _inline(" ".join(paragraph).strip()) + "</p>")
            paragraph.clear()

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if stripped.startswith("```"):
            flush()
            index += 1
            block: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                block.append(html.escape(lines[index]))
                index += 1
            out.append("<pre><code>" + "\n".join(block) + "</code></pre>")
            index += 1
            continue

        if not stripped:
            flush()
            index += 1
            continue

        if stripped.startswith("|") and index + 1 < len(lines) and set(lines[index + 1].strip()) <= set("|-: "):
            flush()
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(lines[index])
                index += 1
            out.append(_table(rows))
            continue

        heading = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if heading:
            flush()
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            index += 1
            continue

        if stripped.startswith(">"):
            flush()
            quote: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote.append(lines[index].strip().lstrip(">").strip())
                index += 1
            out.append("<blockquote>" + _inline(" ".join(quote)) + "</blockquote>")
            continue

        if stripped in {"---", "***", "___"}:
            flush()
            out.append("<hr>")
            index += 1
            continue

        item = re.match(r"^(?:[-*]|\d+\.)\s+(.*)$", stripped)
        if item:
            flush()
            ordered = bool(re.match(r"^\d+\.", stripped))
            items: list[str] = []
            while index < len(lines):
                match = re.match(r"^(?:[-*]|\d+\.)\s+(.*)$", lines[index].strip())
                if not match:
                    break
                items.append(f"<li>{_inline(match.group(1))}</li>")
                index += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(items) + f"</{tag}>")
            continue

        paragraph.append(stripped)
        index += 1

    flush()
    return "\n".join(out)


#: Chapters are rendered in this order; the index links them and each page carries prev/next.
CHAPTERS = [
    ("01-problem", "1. Problem: kayıpsız çeviri ne demek"),
    ("02-mimari", "2. Mimari: boru hattının her parçası"),
    ("03-olcum", "3. Ölçüm disiplini"),
    ("04-hatalar", "4. Hata kataloğu: on dört vaka"),
    ("05-model", "5. Model seçimi ve IBM Docling"),
    ("06-urun", "6. Ürünleşme: motordan uygulamaya"),
    ("07-sinirlar", "7. Dürüst sınırlar ve dersler"),
    ("08-kaynaklar", "8. Dış kaynaklar ve atıflar"),
]

#: A small nav strip under the title: the reader is three pages deep and needs a way back.
NAV_TEMPLATE = """<nav class="story-nav">
  <a href="index.html">Giriş</a>
  {links}
</nav>"""


def _nav(current: str) -> str:
    links = []
    for slug, title in CHAPTERS:
        number = title.split(".")[0]
        if slug == current:
            links.append(f"<span class='here'>{number}</span>")
        else:
            links.append(f"<a href='{slug}.html'>{number}</a>")
    return NAV_TEMPLATE.format(links=" ".join(links))


def _pager(current: str) -> str:
    """Previous / next links, so a chapter can be read straight through."""
    slugs = [slug for slug, _title in CHAPTERS]
    if current not in slugs:
        return ""
    position = slugs.index(current)
    parts = []
    if position > 0:
        parts.append(f"<a href=\"{slugs[position - 1]}.html\">← önceki bölüm</a>")
    else:
        parts.append("<a href=\"index.html\">← giriş</a>")
    if position + 1 < len(slugs):
        parts.append(f"<a href=\"{slugs[position + 1]}.html\">sonraki bölüm →</a>")
    return "<p class=\"pager\">" + " · ".join(parts) + "</p>"


def _chapter_body(path: Path) -> str:
    """A chapter's HTML, with link and image paths re-based for the page it lands on.

    Chapters live in `docs/story/` and reference `architecture.png` beside them, which is the same
    relative path on the page - so only `../screenshots/` (used by the index) needs rewriting. The
    index's table of contents points at `story/01-problem.md` so the links work on GitHub; on the
    page those have to become `01-problem.html`, which is the page that actually exists there.
    """
    body = markdown_to_html(path.read_text(encoding="utf-8"))
    body = body.replace('src="story/', 'src="').replace('src="screenshots/', 'src="../screenshots/')
    return re.sub(r'href="story/([0-9]{2}-[a-z]+)\.md"', r'href="\1.html"', body)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "docs/STORY.md")
    parser.add_argument("--story-dir", type=Path, default=ROOT / "docs/story")
    parser.add_argument("--out", type=Path, default=ROOT / "docs/story/index.html")
    parser.add_argument("--title", default="LayoutKeep — sıfırdan bugüne")
    parser.add_argument(
        "--description",
        default="LayoutKeep'in tam kaydı: ne denendi, ne kırıldı, hangi kök neden ölçüldü.",
    )
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    body = _chapter_body(args.source)
    args.out.write_text(
        TEMPLATE.format(title=html.escape(args.title), description=html.escape(args.description), body=body),
        encoding="utf-8",
    )
    print(f"{args.source.name} -> {args.out.name} ({len(body)} karakter gövde)")

    written = 0
    for slug, title in CHAPTERS:
        source = args.story_dir / f"{slug}.md"
        if not source.exists():
            print(f"  ! {source.name} yok, atlandı")
            continue
        page = _chapter_body(source)
        page = _nav(slug) + page + _pager(slug)
        target = args.story_dir / f"{slug}.html"
        target.write_text(
            TEMPLATE.format(
                title=html.escape(title + " — LayoutKeep"),
                description=html.escape(f"LayoutKeep proje tarihçesi, bölüm: {title}."),
                body=page,
            ),
            encoding="utf-8",
        )
        written += 1
        print(f"  {source.name} -> {target.name} ({len(page)} karakter gövde)")
    print(f"toplam {written} bölüm sayfası + giriş")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
