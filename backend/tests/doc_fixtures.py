"""In-test document fixtures: images with drawn text, PDFs with/without a text layer, hostile files."""

from __future__ import annotations

import io
import shutil
from typing import Any

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.core.scanner import EICAR_SIGNATURE

FONT_PATHS = (
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)

requires_tesseract = pytest.mark.skipif(
    shutil.which("tesseract") is None, reason="tesseract is not installed"
)


def _font(size: int) -> Any:
    for p in FONT_PATHS:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def text_image(lines: list[str], *, width: int = 1400, size: int = 34) -> Image.Image:
    font = _font(size)
    im = Image.new("RGB", (width, 80 + int(size * 1.8) * len(lines)), "white")
    d = ImageDraw.Draw(im)
    for i, line in enumerate(lines):
        d.text((40, 40 + int(size * 1.8) * i), line, fill="black", font=font)
    return im


def png_bytes(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def jpeg_with_exif(size: tuple[int, int] = (2400, 1200)) -> bytes:
    im = Image.new("RGB", size, (200, 180, 150))
    ImageDraw.Draw(im).rectangle((100, 100, 600, 500), fill=(20, 40, 60))
    exif = Image.Exif()
    exif[0x010F] = "SecretCameraMaker"  # Make
    exif[0x0131] = "SecretSoftware"  # Software
    buf = io.BytesIO()
    im.save(buf, "JPEG", exif=exif.tobytes())
    return buf.getvalue()


def image_pdf(im: Image.Image) -> bytes:
    """A scanned-style PDF (image only, no text layer)."""
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "PDF", resolution=150)
    return buf.getvalue()


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def text_pdf(lines: list[str], extra_catalog: str = "") -> bytes:
    """A born-digital PDF with a real text layer (Helvetica, ASCII)."""
    content = "BT /F1 12 Tf 50 760 Td 18 TL\n" + "".join(f"({_esc(ln)}) Tj T*\n" for ln in lines) + "ET"
    objects = [
        f"<< /Type /Catalog /Pages 2 0 R {extra_catalog}>>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(content.encode('latin-1'))} >>\nstream\n{content}\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def javascript_pdf() -> bytes:
    return text_pdf(["Hello"], extra_catalog="/OpenAction << /S /JavaScript /JS (app.alert(1)) >> ")


def eicar_png() -> bytes:
    """A valid PNG carrying the EICAR test string (passes type checks, fails the scanner)."""
    return png_bytes(Image.new("RGB", (10, 10), "white")) + EICAR_SIGNATURE


BIRTH_CERTIFICATE_LINES = [
    "GOVERNMENT OF UTTAR PRADESH",
    "BIRTH CERTIFICATE",
    "Name of Child: Aarav Sharma",
    "Sex: Male",
    "Date of Birth: 14/03/1985",
    "Time of Birth: 04:17 AM",
    "Place of Birth: District Hospital, Lucknow",
    "Father's Name: Rakesh Sharma",
    "Mother's Name: Sunita Sharma",
    "Registration No: B-1985-00432",
    "Date of Registration: 20/03/1985",
    "Aadhaar No: 2345 6789 0123",
]

KUNDLI_LINES = [
    "JANMA KUNDLI",
    "Date of Birth: 12-03-1985",
    "Time of Birth: 04:45 AM",
    "Place of Birth: Lucknow",
    "Nakshatra: Rohini   Pada: 2",
    "Rashi: Vrishabh   Lagna: Makar",
    "Tithi: Shukla Paksha Ekadashi",
    "Ayanamsha: Lahiri",
]

LAND_LINES = [
    "KHATAUNI (RECORD OF RIGHTS)",
    "Village: Rampur   Tehsil: Sadar   District: Gorakhpur",
    "Khata No: 00123   Khasra No: 456/2",
    "Area: 1.250 hectare",
    "Name of Owner: Ram Prasad S/O Shiv Prasad",
    "Mutation No: 77   Date of Mutation: 01/02/2001",
]


def upload(
    client: Any,
    tree_id: str,
    data: bytes,
    *,
    filename: str = "file.png",
    mime: str = "application/octet-stream",
    category: str = "photo",
    title: str = "A document",
    **form: Any,
) -> Any:
    fields = {"category": category, "title": title}
    fields.update({k: str(v) for k, v in form.items() if v is not None})
    return client.post(f"/trees/{tree_id}/documents", files={"file": (filename, data, mime)}, data=fields)


def fetch(client: Any, url: str) -> Any:
    return client.get(url)
