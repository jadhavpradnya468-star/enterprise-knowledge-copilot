import io

import pytest
from docx import Document as DocxDocument

from app.ingestion.chunking import chunk_text
from app.ingestion.extractors import ExtractionError, extract_pages


def test_chunking_respects_size_and_overlaps():
    text = " ".join(f"word{i}" for i in range(400))
    chunks = chunk_text(text, size=200, overlap=40)
    assert len(chunks) > 3
    assert all(len(c) <= 200 for c in chunks)
    assert chunks[0].split()[-1] in chunks[1]  # overlap carries context forward


def test_chunking_rejects_bad_overlap():
    with pytest.raises(ValueError):
        chunk_text("abc", size=10, overlap=10)


def test_txt_and_docx_extraction():
    assert extract_pages(".txt", b"hello world")[0].text == "hello world"
    buf = io.BytesIO()
    d = DocxDocument()
    d.add_paragraph("Leave policy text")
    d.save(buf)
    assert "Leave policy" in extract_pages(".docx", buf.getvalue())[0].text


def _make_pdf(text: str) -> bytes:
    """Build a minimal one-page PDF with a correct xref table."""
    stream = f"BT /F1 12 Tf 10 50 Td ({text}) Tj ET".encode()
    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 100]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length %d>>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer<</Root 1 0 R/Size %d>>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, xref)
    return out


def test_pdf_extraction_with_page_numbers():
    pages = extract_pages(".pdf", _make_pdf("Hello PDF"))
    assert pages[0].page == 1 and "Hello PDF" in pages[0].text


def test_empty_text_is_rejected():
    with pytest.raises(ExtractionError):
        extract_pages(".txt", b"   \n  ")
