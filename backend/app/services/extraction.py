from io import BytesIO
from pathlib import Path
import tempfile

import fitz
import pandas as pd
import pytesseract
from docx import Document as DocxDocument
from PIL import Image

from app.services.chunking import TextSection, clean_text


def extract_text_sections(filename: str, content_type: str | None, content: bytes) -> list[TextSection]:
    suffix = Path(filename).suffix.lower()

    if suffix == ".txt" or (content_type or "").startswith("text/"):
        return _extract_txt(filename, content)
    if suffix == ".pdf" or content_type == "application/pdf":
        return _extract_pdf(filename, content)
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}:
        return _extract_image(filename, content)
    if suffix == ".xlsx":
        return _extract_xlsx(filename, content)
    if suffix == ".csv":
        return _extract_csv(filename, content)
    if suffix == ".docx":
        return _extract_docx(filename, content)

    raise ValueError(f"Unsupported file type for '{filename}'")


def _extract_txt(filename: str, content: bytes) -> list[TextSection]:
    text = content.decode("utf-8", errors="replace")
    return [TextSection(text=clean_text(text), page_number=None, source_reference=filename)]


def _extract_pdf(filename: str, content: bytes) -> list[TextSection]:
    pdf = fitz.open(stream=content, filetype="pdf")
    sections: list[TextSection] = []
    try:
        for page_index, page in enumerate(pdf, start=1):
            text = clean_text(page.get_text("text"))
            if not text:
                pixmap = page.get_pixmap(dpi=200)
                image = Image.open(BytesIO(pixmap.tobytes("png")))
                text = clean_text(pytesseract.image_to_string(image))
            if text:
                sections.append(
                    TextSection(
                        text=text,
                        page_number=page_index,
                        source_reference=f"{filename}#page={page_index}",
                    )
                )
    finally:
        pdf.close()

    if not sections:
        raise ValueError(f"No readable text found in '{filename}'")
    return sections


def _extract_image(filename: str, content: bytes) -> list[TextSection]:
    image = Image.open(BytesIO(content))
    text = clean_text(pytesseract.image_to_string(image))
    if not text:
        raise ValueError(f"No readable text found in '{filename}'")
    return [TextSection(text=text, page_number=None, source_reference=filename)]


def _extract_xlsx(filename: str, content: bytes) -> list[TextSection]:
    sections: list[TextSection] = []
    with tempfile.NamedTemporaryFile(suffix=".xlsx") as temp_file:
        temp_file.write(content)
        temp_file.flush()
        workbook = pd.read_excel(temp_file.name, sheet_name=None, dtype=str)

    for sheet_name, frame in workbook.items():
        frame = frame.fillna("")
        rows = [" | ".join(str(value).strip() for value in row if str(value).strip()) for row in frame.to_numpy()]
        text = clean_text("\n".join(row for row in rows if row))
        if text:
            sections.append(TextSection(text=text, page_number=None, source_reference=f"{filename}#sheet={sheet_name}"))

    if not sections:
        raise ValueError(f"No readable rows found in '{filename}'")
    return sections


def _extract_csv(filename: str, content: bytes) -> list[TextSection]:
    frame = pd.read_csv(BytesIO(content), dtype=str).fillna("")
    rows = [" | ".join(str(value).strip() for value in row if str(value).strip()) for row in frame.to_numpy()]
    text = clean_text("\n".join(row for row in rows if row))
    if not text:
        raise ValueError(f"No readable rows found in '{filename}'")
    return [TextSection(text=text, page_number=None, source_reference=filename)]


def _extract_docx(filename: str, content: bytes) -> list[TextSection]:
    document = DocxDocument(BytesIO(content))
    paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    text = clean_text("\n".join(paragraphs))
    if not text:
        raise ValueError(f"No readable text found in '{filename}'")
    return [TextSection(text=text, page_number=None, source_reference=filename)]
