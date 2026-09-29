"""Image placements on a PDF page, read into DocIR image blocks.

PDF sayfasındaki görsellerin yerlerini okuyup DocIR görsel bloklarına çevirir.
"""

from __future__ import annotations

import base64

from layoutkeep.core.docir import (
    BBox,
    ImageRef,
)


def _extract_images(page) -> list[ImageRef]:
    """The page's pictures, with their bytes, so a rebuilding writer can redraw them.

    The bboxes alone were already read to help decide block roles; the pixels were thrown away.
    That was invisible while the only PDF writer edited a copy of the source and never had to
    reproduce a figure, and it meant every cross-format export lost every image in the document.

    One xref can be placed on a page more than once, so the bytes are decoded once and shared
    between placements.
    """
    doc = page.parent
    decoded: dict[int, tuple[str, str]] = {}
    out: list[ImageRef] = []
    for info in page.get_image_info(xrefs=True):
        xref = info.get("xref", 0)
        if not xref:
            continue
        if xref not in decoded:
            try:
                extracted = doc.extract_image(xref)
            except (RuntimeError, ValueError):
                continue
            decoded[xref] = (
                base64.b64encode(extracted["image"]).decode("ascii"),
                str(extracted.get("ext", "png")).lower(),
            )
        data, fmt = decoded[xref]
        out.append(ImageRef(bbox=BBox(*info["bbox"]), data=data, fmt=fmt))
    return out
