"""OCR engines behind one interface (ADR-0009 §1).

* ``PdfTextLayerEngine`` — reads an embedded text layer with pypdf (born-digital PDFs).
* ``TesseractEngine`` — local ``tesseract`` (default ``eng+hin``); PDFs are rendered with pypdfium2.
  Image bytes are piped via stdin, so decrypted content never touches the filesystem.

No external/cloud OCR provider is used (implementation plan §13.4).
"""

from __future__ import annotations

import io
import logging
import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache

from app.core.config import get_settings

log = logging.getLogger(__name__)

OCR_MAX_PAGES = 20  # OCR at most this many pages per document (bounded CPU per job)
TESSERACT_TIMEOUT_SECONDS = 120


def _tesseract_env() -> dict[str, str]:
    """Run each tesseract single-threaded unless the operator says otherwise.

    The OpenMP builds (Debian/Ubuntu ``tesseract-ocr``) start one busy-waiting thread per core in
    every process. Several OCR jobs at once (RQ workers, or a worker next to the API) then thrash:
    measured on 4 vCPUs, one page took 0.3 s alone but more than 300 s with four in parallel, so
    jobs hit the timeout and documents were marked "OCR failed". With one thread each, four
    parallel runs take 0.3 s apiece. Tesseract's docs recommend this for concurrent instances.
    """
    return {**os.environ, "OMP_THREAD_LIMIT": os.environ.get("OMP_THREAD_LIMIT", "1")}


MIN_TEXT_LAYER_CHARS = 20


class OcrError(Exception):
    pass


@dataclass
class OcrLine:
    line_no: int
    text: str
    confidence: float  # 0..1


@dataclass
class OcrPage:
    page: int  # 1-based
    lines: list[OcrLine] = field(default_factory=list)


@dataclass
class OcrResult:
    pages: list[OcrPage]
    engine: str
    version: str

    @property
    def text(self) -> str:
        return "\n\n".join("\n".join(ln.text for ln in p.lines) for p in self.pages)

    @property
    def confidence(self) -> float:
        lines = [ln for p in self.pages for ln in p.lines]
        if not lines:
            return 0.0
        return round(sum(ln.confidence for ln in lines) / len(lines), 3)

    @property
    def engine_label(self) -> str:
        return f"{self.engine} {self.version}".strip()

    def to_json(self) -> dict:
        return {
            "engine": self.engine,
            "engine_version": self.version,
            "confidence": self.confidence,
            "pages": [
                {
                    "page": p.page,
                    "lines": [
                        {"line_no": ln.line_no, "text": ln.text, "confidence": round(ln.confidence, 3)}
                        for ln in p.lines
                    ],
                }
                for p in self.pages
            ],
        }

    @classmethod
    def from_json(cls, raw: dict) -> OcrResult:
        return cls(
            pages=[
                OcrPage(
                    page=p["page"],
                    lines=[OcrLine(ln["line_no"], ln["text"], float(ln["confidence"])) for ln in p["lines"]],
                )
                for p in raw.get("pages", [])
            ],
            engine=raw.get("engine", ""),
            version=raw.get("engine_version", ""),
        )


class OcrEngine(ABC):
    name: str

    @abstractmethod
    def version(self) -> str: ...

    @abstractmethod
    def supports(self, mime: str) -> bool: ...

    @abstractmethod
    def extract(self, data: bytes, mime: str) -> OcrResult: ...


class PdfTextLayerEngine(OcrEngine):
    name = "pdf-text-layer"

    def version(self) -> str:
        import pypdf

        return f"pypdf-{pypdf.__version__}"

    def supports(self, mime: str) -> bool:
        return mime == "application/pdf"

    def extract(self, data: bytes, mime: str) -> OcrResult:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data), strict=False)
        pages: list[OcrPage] = []
        for i, page in enumerate(reader.pages[:OCR_MAX_PAGES]):
            try:
                text = page.extract_text() or ""
            except Exception as exc:  # malformed content streams
                raise OcrError("the PDF text layer could not be read") from exc
            lines = [ln.strip() for ln in text.splitlines()]
            pages.append(
                OcrPage(page=i + 1, lines=[OcrLine(n + 1, ln, 0.99) for n, ln in enumerate(lines) if ln])
            )
        return OcrResult(pages=pages, engine=self.name, version=self.version())

    @staticmethod
    def has_text(result: OcrResult) -> bool:
        return sum(len(ln.text.strip()) for p in result.pages for ln in p.lines) >= MIN_TEXT_LAYER_CHARS


@lru_cache
def _tesseract_info(cmd: str) -> tuple[str, frozenset[str]]:
    try:
        v = subprocess.run([cmd, "--version"], capture_output=True, timeout=15, check=False)  # noqa: S603
        first = (v.stdout or v.stderr).decode(errors="replace").splitlines()[0]
        langs_out = subprocess.run([cmd, "--list-langs"], capture_output=True, timeout=15, check=False)  # noqa: S603
        langs = frozenset(
            ln.strip()
            for ln in langs_out.stdout.decode(errors="replace").splitlines()[1:]
            if ln.strip() and " " not in ln.strip()
        )
    except (OSError, subprocess.SubprocessError, IndexError) as exc:
        raise OcrError("tesseract is not available") from exc
    return first.replace("tesseract", "").strip() or "unknown", langs


def tesseract_available() -> bool:
    cmd = get_settings().tesseract_cmd
    return shutil.which(cmd) is not None


class TesseractEngine(OcrEngine):
    name = "tesseract"

    def __init__(self, cmd: str | None = None, languages: str | None = None) -> None:
        s = get_settings()
        self.cmd = cmd or s.tesseract_cmd
        self.requested_languages = languages or s.tesseract_languages

    def version(self) -> str:
        return _tesseract_info(self.cmd)[0]

    def languages(self) -> str:
        installed = _tesseract_info(self.cmd)[1]
        wanted = [lang for lang in self.requested_languages.split("+") if lang]
        usable = [lang for lang in wanted if lang in installed] or (["eng"] if "eng" in installed else [])
        if not usable:
            raise OcrError("no usable tesseract language data is installed")
        return "+".join(usable)

    def supports(self, mime: str) -> bool:
        return mime == "application/pdf" or mime.startswith("image/")

    def _page_images(self, data: bytes, mime: str) -> list:  # type: ignore[type-arg]
        from app.modules.documents.previews import load_page_image, pdf_page_count

        if mime == "application/pdf":
            n = min(pdf_page_count(data), OCR_MAX_PAGES)
            return [load_page_image(data, mime, i) for i in range(n)]
        return [load_page_image(data, mime)]

    @staticmethod
    def _prepare(im):  # type: ignore[no-untyped-def]
        gray = im.convert("L")
        w, h = gray.size
        if max(w, h) < 1200:  # small scans/photos: upscale so glyphs are ≥ ~20px tall
            factor = min(3.0, 1800 / max(w, h))
            gray = gray.resize((int(w * factor), int(h * factor)))
        buf = io.BytesIO()
        gray.save(buf, "PNG")
        return buf.getvalue()

    def _run(self, png: bytes, langs: str) -> list[OcrLine]:
        try:
            proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
                [self.cmd, "-", "stdout", "-l", langs, "--psm", "3", "tsv"],
                input=png,
                capture_output=True,
                env=_tesseract_env(),
                timeout=TESSERACT_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise OcrError("OCR timed out") from exc
        except OSError as exc:
            raise OcrError("tesseract is not available") from exc
        if proc.returncode != 0:
            raise OcrError(f"tesseract exited with status {proc.returncode}")
        groups: dict[tuple[str, str, str], list[tuple[str, float]]] = {}
        order: list[tuple[str, str, str]] = []
        for row in proc.stdout.decode("utf-8", errors="replace").splitlines()[1:]:
            cols = row.split("\t")
            if len(cols) != 12 or cols[0] != "5":  # level 5 = word
                continue
            word = cols[11].strip()
            if not word:
                continue
            key = (cols[2], cols[3], cols[4])  # block, paragraph, line
            if key not in groups:
                groups[key] = []
                order.append(key)
            try:
                conf = max(0.0, float(cols[10])) / 100.0
            except ValueError:
                conf = 0.0
            groups[key].append((word, conf))
        lines: list[OcrLine] = []
        for n, key in enumerate(order, start=1):
            words = groups[key]
            lines.append(
                OcrLine(n, " ".join(w for w, _ in words), round(sum(c for _, c in words) / len(words), 3))
            )
        return lines

    def extract(self, data: bytes, mime: str) -> OcrResult:
        langs = self.languages()
        pages = [
            OcrPage(page=i + 1, lines=self._run(self._prepare(im), langs))
            for i, im in enumerate(self._page_images(data, mime))
        ]
        return OcrResult(pages=pages, engine=f"{self.name}[{langs}]", version=self.version())


def run_ocr(data: bytes, mime: str) -> OcrResult:
    """Text layer first for PDFs; Tesseract for images and scanned PDFs."""
    if mime == "application/pdf":
        layer = PdfTextLayerEngine()
        try:
            res = layer.extract(data, mime)
            if PdfTextLayerEngine.has_text(res):
                return res
        except OcrError:
            log.info("PDF text layer unreadable; falling back to tesseract")
    engine = TesseractEngine()
    if not engine.supports(mime):
        raise OcrError(f"OCR is not supported for {mime}")
    return engine.extract(data, mime)
