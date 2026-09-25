"""Preview/thumbnail rendering. Output is a fresh JPEG re-encode: EXIF (GPS, device) is dropped."""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings

THUMBNAIL_MAX = 400
PREVIEW_MAX = 1600
PDF_RENDER_SCALE = 2.0  # ≈144 dpi
JPEG_QUALITY = 85


@dataclass
class Rendered:
    kind: str  # "preview" | "thumbnail"
    data: bytes
    mime: str = "image/jpeg"


def _open_image(data: bytes, mime: str):  # type: ignore[no-untyped-def]
    from PIL import Image, ImageOps

    if mime == "image/heic":
        import pillow_heif

        pillow_heif.register_heif_opener()
    Image.MAX_IMAGE_PIXELS = get_settings().max_image_pixels
    im: Any = Image.open(io.BytesIO(data))
    im.seek(0)  # first frame of multi-page TIFF / animated WebP
    im = ImageOps.exif_transpose(im)  # apply orientation before EXIF is discarded
    return im


def render_pdf_page(data: bytes, page_index: int = 0, scale: float = PDF_RENDER_SCALE):  # type: ignore[no-untyped-def]
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    try:
        page = pdf[page_index]
        try:
            bitmap = page.render(scale=scale)
            return bitmap.to_pil().convert("RGB")
        finally:
            page.close()
    finally:
        pdf.close()


def pdf_page_count(data: bytes) -> int:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    try:
        return len(pdf)
    finally:
        pdf.close()


def load_page_image(data: bytes, mime: str, page_index: int = 0):  # type: ignore[no-untyped-def]
    """First page (or the image itself) as an RGB PIL image."""
    if mime == "application/pdf":
        return render_pdf_page(data, page_index)
    im = _open_image(data, mime)
    if im.mode not in ("RGB", "L"):
        from PIL import Image

        if im.mode in ("RGBA", "LA", "P"):
            rgba = im.convert("RGBA")
            bg = Image.new("RGB", rgba.size, "white")
            bg.paste(rgba, mask=rgba.getchannel("A"))
            im = bg
        else:
            im = im.convert("RGB")
    return im


def _jpeg(im, max_side: int) -> bytes:  # type: ignore[no-untyped-def]
    copy = im.copy()
    copy.thumbnail((max_side, max_side))
    if copy.mode != "RGB":
        copy = copy.convert("RGB")
    buf = io.BytesIO()
    # a new image without `exif=`/`icc_profile=` → no metadata is carried over
    copy.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return buf.getvalue()


def supports_preview(mime: str) -> bool:
    return mime == "application/pdf" or mime.startswith("image/")


def render_previews(data: bytes, mime: str) -> list[Rendered]:
    if not supports_preview(mime):
        return []
    im = load_page_image(data, mime)
    return [Rendered("preview", _jpeg(im, PREVIEW_MAX)), Rendered("thumbnail", _jpeg(im, THUMBNAIL_MAX))]
