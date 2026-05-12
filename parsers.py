"""
Document parsers for PDF, DOCX, XLSX, TXT.
Each parser returns raw text; chunker splits into fixed 1000-char pieces
with control characters stripped.
"""
from __future__ import annotations

import re
import io
from pathlib import Path


CHUNK_SIZE = 1000
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt"}
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB


def _strip_control_chars(text: str) -> str:
    """Remove control characters except newline, carriage return, tab."""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)


def _chunk(text: str, size: int = CHUNK_SIZE) -> list[str]:
    """Split text into fixed-size chunks; drop empty chunks."""
    cleaned = _strip_control_chars(text)
    return [cleaned[i : i + size] for i in range(0, len(cleaned), size) if cleaned[i : i + size].strip()]


def parse_txt(content: bytes) -> str:
    return content.decode("utf-8", errors="replace")


def parse_pdf(content: bytes) -> str:
    import fitz  # PyMuPDF
    doc = fitz.open(stream=content, filetype="pdf")
    pages = [page.get_text() for page in doc]
    doc.close()
    return "\n".join(pages)


def parse_docx(content: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(content))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def parse_xlsx(content: bytes) -> str:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    rows: list[str] = []
    for sheet in wb.worksheets:
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None]
            if cells:
                rows.append("\t".join(cells))
    wb.close()
    return "\n".join(rows)


def parse_xls(content: bytes) -> str:
    import xlrd
    wb = xlrd.open_workbook(file_contents=content)
    rows: list[str] = []
    for sheet in wb.sheets():
        for rx in range(sheet.nrows):
            cells = [str(sheet.cell_value(rx, cx)) for cx in range(sheet.ncols)]
            rows.append("\t".join(cells))
    return "\n".join(rows)


_PARSERS = {
    ".txt":  parse_txt,
    ".pdf":  parse_pdf,
    ".docx": parse_docx,
    ".doc":  parse_docx,
    ".xlsx": parse_xlsx,
    ".xls":  parse_xls,
}


def extract_and_chunk(filename: str, content: bytes) -> list[str]:
    """
    Parse document content and return list of 1000-char text chunks.
    Raises ValueError for unsupported extensions.
    Raises FileTooLargeError if content exceeds MAX_FILE_BYTES.
    """
    if len(content) > MAX_FILE_BYTES:
        raise FileTooLargeError(f"{filename} exceeds 10 MB limit")

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedFormatError(f"Unsupported file type: {ext}")

    parser = _PARSERS[ext]
    raw_text = parser(content)
    return _chunk(raw_text)


class UnsupportedFormatError(Exception):
    pass


class FileTooLargeError(Exception):
    pass
