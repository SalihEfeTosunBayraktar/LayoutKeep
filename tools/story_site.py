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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "docs/STORY.md")
    parser.add_argument("--out", type=Path, default=ROOT / "docs/story/index.html")
    parser.add_argument("--title", default="LayoutKeep — sıfırdan bugüne")
    parser.add_argument(
        "--description",
        default="LayoutKeep'in tam kaydı: ne denendi, ne kırıldı, hangi kök neden ölçüldü.",
    )
    args = parser.parse_args()

    body = markdown_to_html(args.source.read_text(encoding="utf-8"))
    # The Markdown sits in `docs/` and its images are written relative to it (`story/x.png`,
    # `screenshots/y.png`); the page sits one level deeper, so the paths have to be re-based or
    # every image 404s on the published page.
    body = body.replace('src="story/', 'src="').replace('src="screenshots/', 'src="../screenshots/')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        TEMPLATE.format(title=html.escape(args.title), description=html.escape(args.description), body=body),
        encoding="utf-8",
    )
    print(f"{args.source} -> {args.out} ({len(body)} karakter gövde)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
