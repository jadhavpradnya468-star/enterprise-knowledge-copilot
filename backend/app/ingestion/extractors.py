import io
from dataclasses import dataclass

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}


class ExtractionError(Exception):
    """Raised with a message that is safe to show to the user."""


@dataclass
class Page:
    page: int | None
    text: str


def validate_signature(ext: str, data: bytes) -> bool:
    if ext == ".pdf":
        return data[:5] == b"%PDF-"
    if ext == ".docx":
        return data[:2] == b"PK"
    if ext == ".txt":
        return b"\x00" not in data[:4096]
    return False


def extract_pages(ext: str, data: bytes) -> list[Page]:
    if ext == ".txt":
        pages = [Page(None, data.decode("utf-8", errors="replace"))]
    elif ext == ".pdf":
        pages = _pdf(data)
    elif ext == ".docx":
        pages = _docx(data)
    else:
        raise ExtractionError("Unsupported file type.")
    pages = [p for p in pages if p.text.strip()]
    if not pages:
        raise ExtractionError("No extractable text found (scanned documents need OCR).")
    return pages


def _pdf(data: bytes) -> list[Page]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ExtractionError("Encrypted PDFs are not supported.")
        return [Page(i + 1, p.extract_text() or "") for i, p in enumerate(reader.pages)]
    except ExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError("The PDF could not be read.") from exc


def _docx(data: bytes) -> list[Page]:
    from docx import Document as DocxDocument

    try:
        doc = DocxDocument(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError("The DOCX file could not be read.") from exc
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(c.text.strip() for c in row.cells))
    return [Page(None, "\n".join(parts))]  # DOCX has no stable page numbers
