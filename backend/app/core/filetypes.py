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
    elif res.kind in ("audio", "video"):
        _check_media(data, res.mime)
    return res


# ------------------------------------------------------------------ audio / video structure (SEC-6)
_MP4_BOXES = {
    b"ftyp",
    b"moov",
    b"mdat",
    b"free",
    b"skip",
    b"wide",
    b"uuid",
    b"meta",
    b"moof",
    b"mfra",
    b"pdin",
    b"styp",
    b"sidx",
    b"ssix",
    b"prft",
    b"emsg",
    b"udta",
    b"pnot",
    b"PICT",
}


def _bad_media() -> Unprocessable:
    return Unprocessable(
        "The audio/video file is malformed or not what its header claims", code="invalid_media"
    )


def _check_mp4(data: bytes) -> None:
    """Walk ISO-BMFF top-level boxes: sizes must chain exactly to the end and a movie box must exist."""
    pos, seen = 0, set()
    while pos < len(data):
        if pos + 8 > len(data):
            raise _bad_media()
        size = int.from_bytes(data[pos : pos + 4], "big")
        kind = data[pos + 4 : pos + 8]
        header = 8
        if size == 1:
            if pos + 16 > len(data):
                raise _bad_media()
            size, header = int.from_bytes(data[pos + 8 : pos + 16], "big"), 16
        elif size == 0:
            size = len(data) - pos
        if kind not in _MP4_BOXES or size < header or pos + size > len(data):
            raise _bad_media()
        seen.add(kind)
        pos += size
    if b"ftyp" not in seen or not ({b"moov", b"moof"} & seen):
        raise _bad_media()


def _check_riff_wave(data: bytes) -> None:
    declared = int.from_bytes(data[4:8], "little")
    if declared + 8 > len(data) + 1 or b"fmt " not in data[12:64]:
        raise _bad_media()


def _check_mp3(data: bytes) -> None:
    pos = 0
    if data[:3] == b"ID3":
        if len(data) < 10:
            raise _bad_media()
        size = (data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9]
        pos = 10 + size
    # need two consecutive plausible MPEG frame headers
    frames = 0
    while pos + 4 <= len(data) and frames < 2:
        if data[pos] != 0xFF or (data[pos + 1] & 0xE0) != 0xE0:
            raise _bad_media()
        bitrate_idx, sr_idx = data[pos + 2] >> 4, (data[pos + 2] >> 2) & 0x3
        if bitrate_idx in (0, 15) or sr_idx == 3:
            raise _bad_media()
        bitrates = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
        rates = [44100, 48000, 32000]
        length = 144 * bitrates[bitrate_idx] * 1000 // rates[sr_idx] + ((data[pos + 2] >> 1) & 1)
        if length <= 4:
            raise _bad_media()
        pos += length
        frames += 1
    if frames == 0:
        raise _bad_media()


def _check_ogg(data: bytes) -> None:
    if len(data) < 27 or data[4] != 0:  # stream structure version must be 0
        raise _bad_media()
    nsegs = data[26]
    if len(data) < 27 + nsegs:
        raise _bad_media()
    body = sum(data[27 : 27 + nsegs])
    nxt = 27 + nsegs + body
    if nxt < len(data) and data[nxt : nxt + 4] != b"OggS":
        raise _bad_media()


def _check_webm(data: bytes) -> None:
    if b"webm" not in data[:64] and b"matroska" not in data[:64]:
        raise _bad_media()


def _check_media(data: bytes, mime: str) -> None:
    if mime in ("video/mp4", "audio/mp4"):
        _check_mp4(data)
    elif mime == "audio/wav":
        _check_riff_wave(data)
    elif mime == "audio/mpeg":
        _check_mp3(data)
    elif mime == "audio/ogg":
        _check_ogg(data)
    elif mime == "video/webm":
        _check_webm(data)


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
        if _pdf_has_active_content(reader):
            raise Unprocessable(
                "PDFs containing scripts, auto-actions, launch actions or embedded files are not accepted",
                code="unsafe_pdf",
            )
    except PdfReadError as exc:
        raise Unprocessable("The PDF could not be read", code="invalid_pdf") from exc
    if pages > get_settings().max_pdf_pages:
        raise Unprocessable(
            f"PDF has too many pages (max {get_settings().max_pdf_pages})", code="too_many_pages"
        )
    return pages


_UNSAFE_PDF_KEYS = {
    "/JS",
    "/JavaScript",
    "/AA",
    "/Launch",
    "/EmbeddedFile",
    "/EmbeddedFiles",
    "/RichMedia",
    "/XFA",
    "/SubmitForm",
    "/ImportData",
    "/GoToE",
}


def _pdf_has_active_content(reader: object, max_nodes: int = 200_000) -> bool:
    """Walk every reachable PDF object (pypdf decodes #xx name escapes and object streams)."""
    from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, NameObject

    stack: list[object] = [reader.trailer]  # type: ignore[attr-defined]
    seen: set[tuple[int, int]] = set()
    visited = 0
    while stack:
        obj = stack.pop()
        visited += 1
        if visited > max_nodes:
            return True  # pathological structure: refuse rather than guess
        if isinstance(obj, IndirectObject):
            key = (obj.idnum, obj.generation)
            if key in seen:
                continue
            seen.add(key)
            try:
                obj = obj.get_object()
            except Exception:  # dangling reference: nothing to inspect
                obj = None
        if isinstance(obj, DictionaryObject):
            for k, v in obj.items():
                if k in _UNSAFE_PDF_KEYS:
                    return True
                if (
                    k == "/S"
                    and isinstance(v, NameObject)
                    and v in ("/JavaScript", "/Launch", "/SubmitForm", "/ImportData")
                ):
                    return True
                stack.append(v)
        elif isinstance(obj, ArrayObject):
            stack.extend(obj)
    return False


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
