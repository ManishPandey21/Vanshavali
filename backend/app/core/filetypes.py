"""Upload validation: magic-byte sniffing, allowlist and decompression limits (ADR-0004)."""

from __future__ import annotations

import io
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.errors import Unprocessable


@dataclass
class SniffResult:
    mime: str
    kind: str  # pdf | image | audio | video | text
    page_count: int | None = None


_SIGNATURES: list[tuple[bytes, int, str, str]] = [
    (b"%PDF-", 0, "application/pdf", "pdf"),
    (b"\xff\xd8\xff", 0, "image/jpeg", "image"),
    (b"\x89PNG\r\n\x1a\n", 0, "image/png", "image"),
    (b"II*\x00", 0, "image/tiff", "image"),
    (b"MM\x00*", 0, "image/tiff", "image"),
    (b"ID3", 0, "audio/mpeg", "audio"),
    (b"OggS", 0, "audio/ogg", "audio"),
    (b"\x1aE\xdf\xa3", 0, "video/webm", "video"),
]


def sniff(data: bytes) -> SniffResult | None:
    for sig, offset, mime, kind in _SIGNATURES:
        if data[offset : offset + len(sig)] == sig:
            return SniffResult(mime, kind)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return SniffResult("image/webp", "image")
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return SniffResult("audio/wav", "audio")
    if data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"heic", b"heix", b"mif1", b"msf1", b"heim", b"heis", b"hevc"):
            return SniffResult("image/heic", "image")
        if brand in (b"M4A ", b"M4B "):
            return SniffResult("audio/mp4", "audio")
        return SniffResult("video/mp4", "video")
    if data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return SniffResult("audio/mpeg", "audio")
    return None


def sniff_text(data: bytes) -> bool:
    """Plain text (e.g. GEDCOM): decodes as UTF-8/UTF-16/latin-1 and has no NUL bytes outside UTF-16."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return True
    return b"\x00" not in data[:65536]


def validate_upload(data: bytes, *, allow_text: bool = False) -> SniffResult:
    s = get_settings()
    if not data:
        raise Unprocessable("The file is empty", code="empty_file")
    if len(data) > s.max_upload_bytes:
        raise Unprocessable(
            f"The file is larger than {s.max_upload_bytes // (1024 * 1024)} MB", code="file_too_large"
        )
    res = sniff(data)
    if res is None:
        if allow_text and sniff_text(data):
            return SniffResult("text/plain", "text")
        raise Unprocessable(
            "Unsupported or unrecognised file type",
            code="unsupported_type",
            details={
                "allowed": [
                    "PDF",
                    "JPEG",
                    "PNG",
                    "HEIC",
                    "TIFF",
                    "WebP",
                    "MP3",
                    "M4A",
                    "WAV",
                    "OGG",
                    "MP4",
                    "WebM",
                ]
            },
        )
    if res.kind == "pdf":
        res.page_count = _check_pdf(data)
    elif res.kind == "image":
        _check_image(data, res.mime)
    return res


def _check_pdf(data: bytes) -> int:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    lowered = data.lower()
    if b"/javascript" in lowered or b"/js " in lowered or b"/launch" in lowered:
        raise Unprocessable("PDFs containing scripts or launch actions are not accepted", code="unsafe_pdf")
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise Unprocessable("Encrypted/password-protected PDFs are not accepted", code="encrypted_pdf")
        pages = len(reader.pages)
    except PdfReadError as exc:
        raise Unprocessable("The PDF could not be read", code="invalid_pdf") from exc
    if pages > get_settings().max_pdf_pages:
        raise Unprocessable(
            f"PDF has too many pages (max {get_settings().max_pdf_pages})", code="too_many_pages"
        )
    return pages


def _check_image(data: bytes, mime: str) -> None:
    from PIL import Image

    if mime == "image/heic":
        try:
            import pillow_heif

            pillow_heif.register_heif_opener()
        except ImportError:  # pragma: no cover
            return
    Image.MAX_IMAGE_PIXELS = get_settings().max_image_pixels
    try:
        with Image.open(io.BytesIO(data)) as im:
            w, h = im.size
            if w * h > get_settings().max_image_pixels:
                raise Unprocessable("Image dimensions are too large", code="image_too_large")
            im.verify()
    except Image.DecompressionBombError as exc:
        raise Unprocessable("Image dimensions are too large", code="image_too_large") from exc
    except Unprocessable:
        raise
    except Exception as exc:
        raise Unprocessable("The image could not be read", code="invalid_image") from exc
