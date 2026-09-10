"""DOCX generator: creates a fresh DOCX file from a DocIR Document for cross-format export.

DocIR dokümanından sıfırdan Word (.docx) üreten çapraz format dışa aktarım modülü.
"""

from __future__ import annotations

import base64
import html
import zipfile
from dataclasses import dataclass
from pathlib import Path

from layoutkeep.core.docir import Block, BlockRole, Document, ImageRef

_CONTENT_TYPES_TEMPLATE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
{media_defaults}  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""

#: PDF measurements are in points (1/72 inch); OOXML sizes drawings in EMU (1/914400 inch).
_EMU_PER_POINT = 12700
#: Word's default page text width, used to keep a wide figure inside the margins.
_MAX_IMAGE_WIDTH_EMU = 5486400

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""


def _paragraph_xml(block: Block) -> str:
    # Bloktan Word paragraf XML'i üretir / Builds Word paragraph XML from block
    text = html.escape(block.text.strip())
    if not text:
        return ""
    bold_tag = "<w:b/>" if block.dominant_style().bold else ""
    italic_tag = "<w:i/>" if block.dominant_style().italic else ""
    size = round(block.dominant_style().size * 2) if block.dominant_style().size > 0 else 22
    if block.role in (BlockRole.TITLE, BlockRole.HEADING):
        bold_tag = "<w:b/>"
        size = 32 if block.role == BlockRole.TITLE else 28
    # DocIR carries alignment now (left/center/right/justify); Word maps it to <w:jc>.
    jc = "" if block.align in ("", "left") else f'<w:jc w:val="{block.align}"/>'

    return (
        "<w:p>"
        f"<w:pPr>{jc}<w:rPr>{bold_tag}{italic_tag}<w:sz w:val=\"{size}\"/></w:rPr></w:pPr>"
        f"<w:r><w:rPr>{bold_tag}{italic_tag}<w:sz w:val=\"{size}\"/></w:rPr>"
        f"<w:t xml:space=\"preserve\">{text}</w:t></w:r>"
        "</w:p>"
    )


@dataclass(slots=True)
class _PackagedImage:
    """One image on its way into the package: its part name, relationship id and bytes."""

    part_name: str
    rel_id: str
    payload: bytes
    width_emu: int
    height_emu: int


def _collect_images(doc: Document) -> tuple[dict[int, _PackagedImage], list[_PackagedImage]]:
    """Assign a package part and relationship id to every image in the document.

    A DOCX carries pictures as separate parts wired up through word/_rels/document.xml.rels.
    None of that existed, so the package held three files and every figure in the source was
    dropped without a word - a 23-image report exported to Word contained no images at all.
    """
    by_id: dict[int, _PackagedImage] = {}
    ordered: list[_PackagedImage] = []
    for _page_number, page in enumerate(doc.pages, 1):
        for _image_number, image in enumerate(page.images, 1):
            if not image.data:
                continue
            width = max(1, int(image.bbox.width * _EMU_PER_POINT))
            height = max(1, int(image.bbox.height * _EMU_PER_POINT))
            if width > _MAX_IMAGE_WIDTH_EMU:
                height = max(1, int(height * _MAX_IMAGE_WIDTH_EMU / width))
                width = _MAX_IMAGE_WIDTH_EMU
            packaged = _PackagedImage(
                part_name=f"media/image{len(ordered) + 1}.{image.fmt}",
                rel_id=f"rIdImg{len(ordered) + 1}",
                payload=base64.b64decode(image.data),
                width_emu=width,
                height_emu=height,
            )
            by_id[id(image)] = packaged
            ordered.append(packaged)
    return by_id, ordered


def _drawing_xml(packaged: _PackagedImage, index: int) -> str:
    # Görseli satır içi çizim olarak yerleştirir / Places the image as an inline drawing
    return (
        "<w:p><w:r><w:drawing>"
        f'<wp:inline distT="0" distB="0" distL="0" distR="0" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
        f'<wp:extent cx="{packaged.width_emu}" cy="{packaged.height_emu}"/>'
        f'<wp:docPr id="{index}" name="Picture {index}"/>'
        '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f'<pic:nvPicPr><pic:cNvPr id="{index}" name="Picture {index}"/><pic:cNvPicPr/>'
        "</pic:nvPicPr>"
        '<pic:blipFill><a:blip xmlns:r="http://schemas.openxmlformats.org/officeDocument/'
        f'2006/relationships" r:embed="{packaged.rel_id}"/><a:stretch><a:fillRect/></a:stretch>'
        "</pic:blipFill>"
        '<pic:spPr><a:xfrm><a:off x="0" y="0"/>'
        f'<a:ext cx="{packaged.width_emu}" cy="{packaged.height_emu}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
        "</pic:pic></a:graphicData></a:graphic></wp:inline>"
        "</w:drawing></w:r></w:p>"
    )


def _document_rels_xml(images: list[_PackagedImage]) -> str:
    entries = "".join(
        f'<Relationship Id="{img.rel_id}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        f'Target="{img.part_name}"/>'
        for img in images
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{entries}</Relationships>"
    )


def _content_types_xml(images: list[_PackagedImage]) -> str:
    extensions = sorted({img.part_name.rsplit(".", 1)[-1] for img in images})
    defaults = "".join(
        f'  <Default Extension="{ext}" ContentType="image/{ext}"/>\n' for ext in extensions
    )
    return _CONTENT_TYPES_TEMPLATE.format(media_defaults=defaults)


def _build_document_xml(doc: Document, packaged_by_id: dict[int, _PackagedImage]) -> str:
    # Tüm doküman gövdesini oluşturur / Builds entire document XML body
    paragraphs: list[str] = []
    drawing_index = 1
    for page in doc.pages:
        for item in page.content_in_reading_order():
            if isinstance(item, ImageRef):
                packaged = packaged_by_id.get(id(item))
                if packaged is not None:
                    paragraphs.append(_drawing_xml(packaged, drawing_index))
                    drawing_index += 1
                continue
            p_xml = _paragraph_xml(item)
            if p_xml:
                paragraphs.append(p_xml)

    body_inner = "\n    ".join(paragraphs)
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n"
        "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">\n"
        f"  <w:body>\n    {body_inner}\n    <w:sectPr/>\n  </w:body>\n"
        "</w:document>"
    )


def generate_docx_from_docir(doc: Document, out_path: str | Path) -> None:
    # DocIR dokümanından yeni DOCX dosyası üretir / Generates new DOCX file from DocIR
    packaged_by_id, images = _collect_images(doc)
    doc_xml = _build_document_xml(doc, packaged_by_id)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types_xml(images).strip())
        zf.writestr("_rels/.rels", _ROOT_RELS.strip())
        zf.writestr("word/document.xml", doc_xml.strip())
        if images:
            zf.writestr("word/_rels/document.xml.rels", _document_rels_xml(images))
            for image in images:
                zf.writestr(f"word/{image.part_name}", image.payload)
