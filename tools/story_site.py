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
<html lang="{lang}">
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
  .story-langs {{ display: flex; gap: .4rem; align-items: center; margin: 0 0 1.2rem; font-size: .88rem; }}
  .story-langs a, .story-langs .here {{ padding: .1rem .5rem; border: 1px solid var(--border);
                                        border-radius: 999px; text-decoration: none; }}
  .story-langs .here {{ background: var(--accent); color: #fff; border-color: var(--accent); font-weight: 600; }}
  .untranslated {{ border-left: 3px solid var(--accent); background: var(--card);
                   padding: .5rem .8rem; border-radius: 0 8px 8px 0; }}
  .pager {{ display: flex; justify-content: space-between; gap: 1rem; margin: 3rem 0 0;
            padding-top: 1.2rem; border-top: 1px solid var(--border); font-size: .95rem; }}
  footer {{ margin-top: 3rem; padding-top: 1.2rem; border-top: 1px solid var(--border); color: var(--muted); font-size: .9rem; }}
</style>
</head>
<body>
<main>
<a class="home" href="{home}">← LayoutKeep</a>
{switcher}
{body}
<footer>
  {footer}
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


#: Chapters are rendered in this order. The titles live with the languages below: a translated
#: page showing a Turkish title would be worse than not translating it at all.
CHAPTERS = [
    "01-problem",
    "02-mimari",
    "03-olcum",
    "04-hatalar",
    "05-model",
    "06-urun",
    "07-sinirlar",
    "08-kaynaklar",
]

#: The languages the story is published in. Turkish is the original and lives in `docs/story/`;
#: the others live beside it in their own directory (`docs/story/en/04-hatalar.md`). A chapter
#: without a translation falls back to the original with a visible note, so a half-finished
#: translation reads as half-finished rather than as a broken page - and adding a language is one
#: entry here plus the translated files, nothing else.
LANGUAGES: dict[str, dict] = {
    "tr": {
        "label": "Türkçe",
        "dir": "",
        "index_title": "Giriş",
        "page_title": "LayoutKeep — sıfırdan bugüne",
        "description": "LayoutKeep'in tam kaydı: ne denendi, ne kırıldı, hangi kök neden ölçüldü.",
        "prev": "← önceki bölüm",
        "next": "sonraki bölüm →",
        "intro": "← giriş",
        "missing": "",
        "footer": (
            'Bu sayfa <code>docs/STORY.md</code> dosyasından <code>tools/story_site.py</code> ile '
            'üretildi. Karşılaştırma sitesi: <a href="{root}comparison/">orijinal ↔ çeviri</a>.'
        ),
        "titles": {
            "01-problem": "1. Problem: kayıpsız çeviri ne demek",
            "02-mimari": "2. Mimari: boru hattının her parçası",
            "03-olcum": "3. Ölçüm disiplini",
            "04-hatalar": "4. Hata kataloğu: on altı vaka",
            "05-model": "5. Model seçimi ve IBM Docling",
            "06-urun": "6. Ürünleşme: motordan uygulamaya",
            "07-sinirlar": "7. Dürüst sınırlar ve dersler",
            "08-kaynaklar": "8. Dış kaynaklar ve atıflar",
        },
    },
    "en": {
        "label": "English",
        "dir": "en",
        "index_title": "Introduction",
        "page_title": "LayoutKeep — from nothing to now",
        "description": "The full record of LayoutKeep: what was tried, what broke, which root cause was measured.",
        "prev": "← previous chapter",
        "next": "next chapter →",
        "intro": "← introduction",
        "missing": (
            "<p class=\"untranslated\"><em>This chapter has not been translated yet; the Turkish "
            "original is shown below.</em></p>\n"
        ),
        "footer": (
            'This page is generated from <code>docs/STORY.md</code> by '
            '<code>tools/story_site.py</code>. Comparison site: '
            '<a href="{root}comparison/">original ↔ translation</a>.'
        ),
        "titles": {
            "01-problem": "1. The problem: what lossless translation means",
            "02-mimari": "2. Architecture: every part of the pipeline",
            "03-olcum": "3. Measurement discipline",
            "04-hatalar": "4. The bug catalogue: sixteen cases",
            "05-model": "5. Choosing the model, and IBM Docling",
            "06-urun": "6. From engine to product",
            "07-sinirlar": "7. Honest limits and lessons",
            "08-kaynaklar": "8. External sources and citations",
        },
    },
    "de": {
        "label": "Deutsch",
        "dir": "de",
        "index_title": "Einführung",
        "page_title": "LayoutKeep — von null bis heute",
        "description": "Die vollständige Aufzeichnung von LayoutKeep: was versucht wurde, was brach, welche Ursache gemessen wurde.",
        "prev": "← voriges Kapitel",
        "next": "nächstes Kapitel →",
        "intro": "← Einführung",
        "missing": (
            "<p class=\"untranslated\"><em>Dieses Kapitel ist noch nicht übersetzt; unten steht das "
            "türkische Original.</em></p>\n"
        ),
        "footer": (
            'Diese Seite wird von <code>tools/story_site.py</code> aus <code>docs/STORY.md</code> '
            'erzeugt. Vergleichsseite: <a href="{root}comparison/">Original ↔ Übersetzung</a>.'
        ),
        "titles": {
            "01-problem": "1. Das Problem: Was verlustfreie Übersetzung bedeutet",
            "02-mimari": "2. Architektur: jedes Teil der Pipeline",
            "03-olcum": "3. Messdisziplin",
            "04-hatalar": "4. Der Fehlerkatalog: sechzehn Fälle",
            "05-model": "5. Die Modellwahl und IBM Docling",
            "06-urun": "6. Vom Motor zum Produkt",
            "07-sinirlar": "7. Ehrliche Grenzen und Lehren",
            "08-kaynaklar": "8. Externe Quellen und Zitate",
        },
    },
}

#: A small nav strip under the title: the reader is three pages deep and needs a way back.
NAV_TEMPLATE = """<nav class="story-nav">
  <a href="index.html">{index}</a>
  {links}
</nav>"""

#: The language switch, one link per language, the current one marked. Every page carries it, so a
#: reader who lands on a chapter in the wrong language is one click from the right one.
SWITCH_TEMPLATE = """<nav class="story-langs">
  {links}
</nav>"""


def _switch(language: str, slug: str | None) -> str:
    """The language strip for a page, with paths relative to that page's own directory."""
    links = []
    for code, spec in LANGUAGES.items():
        page = f"{slug}.html" if slug else "index.html"
        if code == language:
            links.append(f"<span class='here'>{spec['label']}</span>")
            continue
        if spec["dir"]:
            target = f"../{spec['dir']}/{page}" if language != "tr" else f"{spec['dir']}/{page}"
        else:
            target = f"../{page}" if language != "tr" else page
        links.append(f"<a href='{target}'>{spec['label']}</a>")
    return SWITCH_TEMPLATE.format(links=" ".join(links))


def _nav(language: str, current: str) -> str:
    spec = LANGUAGES[language]
    links = []
    for slug in CHAPTERS:
        number = spec["titles"][slug].split(".")[0]
        if slug == current:
            links.append(f"<span class='here'>{number}</span>")
        else:
            links.append(f"<a href='{slug}.html'>{number}</a>")
    return NAV_TEMPLATE.format(index=spec["index_title"], links=" ".join(links))


def _pager(language: str, current: str) -> str:
    """Previous / next links, so a chapter can be read straight through."""
    spec = LANGUAGES[language]
    if current not in CHAPTERS:
        return ""
    position = CHAPTERS.index(current)
    parts = []
    if position > 0:
        parts.append(f"<a href=\"{CHAPTERS[position - 1]}.html\">{spec['prev']}</a>")
    else:
        parts.append(f"<a href=\"index.html\">{spec['intro']}</a>")
    if position + 1 < len(CHAPTERS):
        parts.append(f"<a href=\"{CHAPTERS[position + 1]}.html\">{spec['next']}</a>")
    return "<p class=\"pager\">" + " · ".join(parts) + "</p>"


def _chapter_body(path: Path, depth: int) -> str:
    """A chapter's HTML, with link and image paths re-based for the page it lands on.

    Chapters live in `docs/story/` and reference `architecture.png` beside them, which is the same
    relative path on the page in the original language - and one level up from a translated page,
    which sits in its own directory. The index's table of contents points at `story/01-problem.md`
    so the links work on GitHub; on the page those have to become `01-problem.html`.
    """
    body = markdown_to_html(path.read_text(encoding="utf-8"))
    up = "../" * depth
    body = body.replace('src="story/', f'src="{up}').replace(
        'src="screenshots/', f'src="{up}../screenshots/'
    )
    if depth:
        # A translated page sits one level below the original, so a bare asset path
        # (`architecture.png`, which the original language can leave alone because the file is
        # right beside the page) has to step up too. Verified by resolving every link in every
        # generated page against the disk: three of them were broken before this.
        def _step_up(match: re.Match[str]) -> str:
            target = match.group(1)
            if target.startswith(("../", "/", "http", "data:", "#")):
                return match.group(0)
            return f'src="{up}{target}"'

        body = re.sub(r'src="([^"]+)"', _step_up, body)
    return re.sub(r'href="story/([0-9]{2}-[a-z]+)\.md"', r'href="\1.html"', body)


def _source_for(language: str, slug: str | None, source: Path, story_dir: Path) -> tuple[Path, bool]:
    """The Markdown to render for a page, and whether it is a fallback.

    The index is `docs/STORY.md`; a chapter is `docs/story/<slug>.md`. A translation sits in the
    language's own directory with the same name (`index.md`, `04-hatalar.md`). When it is missing,
    the page falls back to the closest language that has one - English before the Turkish original -
    so a German reader waiting for a translation gets the language most of them read anyway.
    """
    spec = LANGUAGES[language]
    original = source if slug is None else story_dir / f"{slug}.md"
    name = "index.md" if slug is None else f"{slug}.md"
    if not spec["dir"]:
        return original, False
    candidates = [story_dir / spec["dir"] / name]
    if language != "en":
        candidates.append(story_dir / "en" / name)
    candidates.append(original)
    for candidate in candidates[:-1]:
        if candidate.exists():
            return candidate, candidate != candidates[0]
    return original, True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "docs/STORY.md")
    parser.add_argument("--story-dir", type=Path, default=ROOT / "docs/story")
    parser.add_argument("--only", default="", help="render one language only (default: all)")
    args = parser.parse_args()

    written = 0
    for code, spec in LANGUAGES.items():
        if args.only and code != args.only:
            continue
        out_dir = args.story_dir / spec["dir"] if spec["dir"] else args.story_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        depth = 1 if spec["dir"] else 0
        root = "../" * (depth + 1)
        home = "../" * (depth + 1)

        source, fell_back = _source_for(code, None, args.source, args.story_dir)
        body = _chapter_body(source, depth)
        if fell_back and spec["missing"]:
            body = spec["missing"] + body
        (out_dir / "index.html").write_text(
            TEMPLATE.format(
                lang=code,
                title=html.escape(spec["page_title"]),
                description=html.escape(spec["description"]),
                home=home,
                switcher=_switch(code, None),
                body=body,
                footer=spec["footer"].format(root=root),
            ),
            encoding="utf-8",
        )
        print(f"[{code}] {source.name} -> {out_dir.name}/index.html ({len(body)} karakter gövde)")
        written += 1

        for slug in CHAPTERS:
            source, fell_back = _source_for(code, slug, args.source, args.story_dir)
            if not source.exists():
                print(f"  ! {source} yok, atlandı")
                continue
            page = _chapter_body(source, depth)
            if fell_back and spec["missing"]:
                page = spec["missing"] + page
            title = spec["titles"][slug]
            (out_dir / f"{slug}.html").write_text(
                TEMPLATE.format(
                    lang=code,
                    title=html.escape(f"{title} — LayoutKeep"),
                    description=html.escape(f"{title} — {spec['page_title']}"),
                    home=home,
                    switcher=_switch(code, slug),
                    body=_nav(code, slug) + page + _pager(code, slug),
                    footer=spec["footer"].format(root=root),
                ),
                encoding="utf-8",
            )
            written += 1
        if fell_back:
            print(f"[{code}] {written} sayfa yazıldı (eksik çeviriler orijinalden)")
    print(f"toplam {written} sayfa, {len(LANGUAGES)} dil")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
