from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from pathlib import Path
from io import BytesIO
import mimetypes
import os
import re
import uuid
import zipfile
import xml.etree.ElementTree as ET


UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "data/uploads"))


TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".json", ".csv", ".tsv", ".yaml", ".yml"}
DOCX_EXTENSION = ".docx"
PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


@dataclass
class ExtractedFile:
    filename: str
    content_type: str
    size: int
    path: str
    extracted_text: str
    extraction_status: str
    extraction_notes: str


def safe_filename(filename: str) -> str:
    base = Path(filename or "upload.bin").name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return cleaned or "upload.bin"


def store_and_extract_file(filename: str, content: bytes, content_type: str = "") -> ExtractedFile:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = safe_filename(filename)
    stored_name = f"{uuid.uuid4().hex}_{safe_name}"
    path = UPLOAD_DIR / stored_name
    path.write_bytes(content)

    guessed_type = content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    suffix = Path(safe_name).suffix.lower()
    extracted_text, status, notes = extract_text(safe_name, content, guessed_type)
    return ExtractedFile(
        filename=safe_name,
        content_type=guessed_type,
        size=len(content),
        path=str(path),
        extracted_text=extracted_text,
        extraction_status=status,
        extraction_notes=notes,
    )


def extract_text(filename: str, content: bytes, content_type: str = "") -> tuple[str, str, str]:
    suffix = Path(filename).suffix.lower()
    if suffix in TEXT_EXTENSIONS or content_type.startswith("text/"):
        return decode_text(content), "extracted", "Text content extracted directly."
    if suffix == DOCX_EXTENSION:
        text = extract_docx_text(content)
        if text.strip():
            return text, "extracted", "DOCX text extracted from document XML."
        return "", "needs_ai", "DOCX text extraction produced no content."
    if suffix in PDF_EXTENSIONS:
        return (
            f"PDF file uploaded: {filename}. A multimodal/document AI extractor should read this file for full content.",
            "needs_ai",
            "PDF binary stored. Add a document AI extractor for full parsing.",
        )
    if suffix in IMAGE_EXTENSIONS or content_type.startswith("image/"):
        return (
            f"Image file uploaded: {filename}. A multimodal AI extractor should inspect this image for UI, copy, and visual assertions.",
            "needs_ai",
            "Image binary stored. Add multimodal AI or OCR extraction for full parsing.",
        )
    return (
        f"File uploaded: {filename}. No built-in extractor is available for this type.",
        "needs_ai",
        "Binary stored. Add a specialized extractor for this file type.",
    )


def decode_text(content: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def extract_docx_text(content: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            xml = archive.read("word/document.xml")
    except Exception:
        return ""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return ""
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        texts = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
        joined = unescape("".join(texts)).strip()
        if joined:
            paragraphs.append(joined)
    return "\n".join(paragraphs)
