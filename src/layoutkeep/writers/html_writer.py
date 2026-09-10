"""HTML writer: renders a DocIR Document as a modern standalone HTML5 document.

DocIR dokümanını modern ve bağımsız bir HTML5 dosyası olarak dışa aktarır.
"""

from __future__ import annotations

import html
from pathlib import Path

from layoutkeep.core.docir import Block, BlockRole, Document, ImageRef, Page, Span

_ROLE_TAGS: dict[BlockRole, str] = {
    BlockRole.TITLE: "h1",
    BlockRole.HEADING: "h2",
    BlockRole.BODY: "p",
    BlockRole.LIST: "li",
    BlockRole.CAPTION: "figcaption",
    BlockRole.FOOTNOTE: "aside",
    BlockRole.CODE: "pre",
    BlockRole.HEADER: "header",
    BlockRole.FOOTER: "footer",
}

_BASE_CSS = """
:root {
  --lk-font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
  --lk-font-mono: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
  --lk-bg: #f8fafc;
  --lk-page-bg: #ffffff;
  --lk-text: #0f172a;
  --lk-muted: #64748b;
  --lk-border: #e2e8f0;
  --lk-accent: #2563eb;
}
@media (prefers-color-scheme: dark) {
  :root {
    --lk-bg: #0b0f19;
    --lk-page-bg: #111827;
    --lk-text: #f3f4f6;
    --lk-muted: #9ca3af;
    --lk-border: #374151;
    --lk-accent: #60a5fa;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 2rem 1rem;
  background-color: var(--lk-bg);
  color: var(--lk-text);
  font-family: var(--lk-font);
  line-height: 1.6;
}
.page-container {
  max-width: 800px;
  margin: 0 auto 2rem auto;
  background: var(--lk-page-bg);
  padding: 3rem;
  border-radius: 8px;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
  border: 1px solid var(--lk-border);
}
h1, h2, h3, h4, h5, h6 {
  color: var(--lk-text);
  line-height: 1.3;
  margin-top: 1.5em;
  margin-bottom: 0.5em;
}
h1 { font-size: 2rem; border-bottom: 2px solid var(--lk-border); padding-bottom: 0.3em; }
h2 { font-size: 1.5rem; }
p { margin-top: 0; margin-bottom: 1em; }
li { margin-bottom: 0.3em; }
ul, ol { margin-top: 0; margin-bottom: 1em; padding-left: 1.5em; }
pre {
  background: rgba(0, 0, 0, 0.05);
  padding: 1rem;
  border-radius: 6px;
  font-family: var(--lk-font-mono);
  overflow-x: auto;
}
aside.footnote {
  font-size: 0.875rem;
  color: var(--lk-muted);
  border-top: 1px solid var(--lk-border);
  margin-top: 1.5em;
  padding-top: 0.5em;
}
.page-number {
  font-size: 0.75rem;
  color: var(--lk-muted);
  text-align: center;
  margin-top: 2rem;
}
img {
  max-width: 100%;
  height: auto;
  display: block;
  margin: 1em auto;
}

@media print {
  body { background: transparent; padding: 0; }
  .page-container {
    box-shadow: none;
    border: none;
    padding: 0;
    max-width: 100%;
    page-break-after: always;
  }
}
"""


def _render_span(span: Span) -> str:
    # Tek bir metin parçasını (Span) stilini koruyarak HTML'e çevirir / Renders styled span
    txt = html.escape(span.text)
    if not txt:
        return ""
    if span.style.bold:
        txt = f"<strong>{txt}</strong>"
    if span.style.italic:
        txt = f"<em>{txt}</em>"
    styles: list[str] = []
    if span.style.color and span.style.color != "#000000":
        styles.append(f"color: {span.style.color}")
    if span.style.size > 0:
        styles.append(f"font-size: {span.style.size:.1f}pt")
    if styles:
        txt = f'<span style="{"; ".join(styles)}">{txt}</span>'
    return txt


def _render_block(block: Block) -> str:
    # Metin bloğunu stilleri ve satırları koruyarak HTML etiketine dönüştürür / Converts block to styled HTML
    lines_html: list[str] = []
    for line in block.lines:
        line_str = "".join(_render_span(span) for span in line.spans)
        if line_str:
            lines_html.append(line_str)

    content = "<br/>\n".join(lines_html) if lines_html else html.escape(block.text.strip())
    if not content.strip():
        return ""

    tag = _ROLE_TAGS.get(block.role, "p")
    extra_class = " class=\"footnote\"" if block.role == BlockRole.FOOTNOTE else ""
    align_attr = f" style=\"text-align: {block.align};\"" if block.align and block.align != "left" else ""
    return f"<{tag}{extra_class}{align_attr}>{content}</{tag}>"


def _render_page(page: Page) -> str:
    # Tek bir sayfanın içeriğini işler / Processes contents of a single page
    blocks_html: list[str] = []
    in_list = False

    for block in page.content_in_reading_order():
        if isinstance(block, ImageRef):
            # A figure the source carried. Inline as a data URI so the export stays one file.
            if in_list:
                blocks_html.append("</ul>")
                in_list = False
            if block.data:
                blocks_html.append(f'<img src="{block.data_uri}" alt=""/>')
            continue
        if block.role == BlockRole.LIST:
            if not in_list:
                blocks_html.append("<ul>")
                in_list = True
            blocks_html.append(_render_block(block))
        else:
            if in_list:
                blocks_html.append("</ul>")
                in_list = False
            rendered = _render_block(block)
            if rendered:
                blocks_html.append(rendered)

    if in_list:
        blocks_html.append("</ul>")

    blocks_html.append(f'<div class="page-number">{page.number}</div>')
    body_content = "\n  ".join(blocks_html)
    return f'<section class="page-container">\n  {body_content}\n</section>'


def write_html(doc: Document, source_path: str | Path, out_path: str | Path) -> None:
    # DocIR dokümanını HTML5 dosyasına yazar / Writes DocIR document to HTML5 file
    title_meta = doc.metadata.get("title") if isinstance(doc.metadata, dict) else None
    title = html.escape(title_meta or Path(source_path).stem)
    lang = doc.target_lang or "en"
    pages_html = "\n".join(_render_page(page) for page in doc.pages)

    full_html = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{title}</title>
  <style>{_BASE_CSS}</style>
</head>
<body>
{pages_html}
</body>
</html>
"""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(full_html, encoding="utf-8")
