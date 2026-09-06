"""Bounded, isolated extraction. The child has no application state or credentials.

This is process isolation and parser resource limiting, not an OS security sandbox.
The child never follows document links, opens attachments, or executes embedded content.
"""

import base64
import hashlib
import io
import json
import os
import socket
import subprocess
import sys
import zipfile
from pathlib import Path

MAX_BINARY_BYTES = 10 * 1024 * 1024
MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_ZIP_BYTES = 32 * 1024 * 1024
TIMEOUT_SECONDS = 20
MEDIA_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class ExtractionError(Exception):
    pass


def _assemble(parts):
    text, anchors, offset = [], [], 0
    for ref, label, value in parts:
        value = value.replace("\r\n", "\n").strip()
        if not value:
            continue
        if "\x00" in value:
            raise ExtractionError("INVALID_DOCUMENT")
        if text:
            offset += 2
        anchors.append({"ref": ref, "label": label, "start": offset, "end": offset + len(value)})
        text.append(value)
        offset += len(value)
        if offset > MAX_TEXT_BYTES:
            raise ExtractionError("EXTRACTED_TEXT_TOO_LARGE")
    joined = "\n\n".join(text)
    if len(joined.encode()) > MAX_TEXT_BYTES:
        raise ExtractionError("EXTRACTED_TEXT_TOO_LARGE")
    return {"text": joined, "anchors": anchors}


def _extract(content, extension):
    if extension == ".pdf":
        from pypdf import PdfReader

        if not content.startswith(b"%PDF-"):
            raise ExtractionError("UNSUPPORTED_DOCUMENT")
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise ExtractionError("ENCRYPTED_DOCUMENT")
        if len(reader.pages) > 300:
            raise ExtractionError("DOCUMENT_TOO_COMPLEX")

        def pages():
            for number, page in enumerate(reader.pages, 1):
                stream = page.get_contents()
                if stream is not None and len(stream.get_data()) > MAX_ZIP_BYTES:
                    raise ExtractionError("DOCUMENT_TOO_COMPLEX")
                yield f"page:{number}", f"Page {number}", page.extract_text() or ""

        result = _assemble(pages())
        if not result["text"]:
            raise ExtractionError("OCR_REQUIRED")
        return result
    if extension == ".docx":
        from docx import Document
        from docx.oxml.ns import qn
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 1000 or sum(x.file_size for x in entries) > MAX_ZIP_BYTES:
                raise ExtractionError("DOCUMENT_TOO_COMPLEX")
            if any(x.flag_bits & 1 for x in entries):
                raise ExtractionError("ENCRYPTED_DOCUMENT")
            if any(x.file_size > max(x.compress_size, 1) * 200 for x in entries):
                raise ExtractionError("DOCUMENT_TOO_COMPLEX")
            if "word/document.xml" not in archive.namelist():
                raise ExtractionError("UNSUPPORTED_DOCUMENT")
            # Office ZIP parts stay in memory; reject entity/DTD definitions before lxml sees them.
            for entry in entries:
                if entry.filename.lower().endswith((".xml", ".rels")):
                    data = archive.read(entry)
                    # XML can use UTF-16; the NUL removal also detects its declaration spellings.
                    lowered = data.replace(b"\x00", b"").lower()
                    if b"<!doctype" in lowered or b"<!entity" in lowered:
                        raise ExtractionError("UNSAFE_DOCUMENT_XML")
        doc = Document(io.BytesIO(content))
        parts, paragraph, table = [], 0, 0
        for element in doc.element.body.iterchildren():
            if element.tag == qn("w:p"):
                paragraph += 1
                parts.append(
                    (
                        f"paragraph:{paragraph}",
                        f"Paragraph {paragraph}",
                        Paragraph(element, doc).text,
                    )
                )
            elif element.tag == qn("w:tbl"):
                table += 1
                for number, value in enumerate(Table(element, doc).rows, 1):
                    parts.append(
                        (
                            f"table:{table}:row:{number}",
                            f"Table {table}, row {number}",
                            " | ".join(cell.text for cell in value.cells),
                        )
                    )
        result = _assemble(parts)
        if not result["text"]:
            raise ExtractionError("EMPTY_OR_BINARY_DOCUMENT")
        return result
    raise ExtractionError("UNSUPPORTED_DOCUMENT")


def parse_document(filename, content, content_type="application/octet-stream"):
    """Return normalized text, stable anchors, original hash and canonical media type."""
    from app.errors import DomainError

    extension = Path(filename).suffix.lower()
    if (
        not filename
        or len(filename) > 200
        or any(x in filename for x in ("/", "\\", "\x00", "\r", "\n"))
        or extension not in MEDIA_TYPES
        or content_type.split(";", 1)[0].lower()
        not in {MEDIA_TYPES[extension], "application/octet-stream", "text/plain"}
    ):
        raise DomainError("UNSUPPORTED_DOCUMENT", 415)
    if extension in {".txt", ".md"}:
        try:
            text = content.decode("utf-8").replace("\r\n", "\n").strip()
        except UnicodeError as exc:
            raise DomainError("INVALID_UTF8", 422) from exc
        if not text or "\x00" in text:
            raise DomainError("EMPTY_OR_BINARY_DOCUMENT", 422)
        result = {"text": text, "anchors": []}
    else:
        if len(content) > MAX_BINARY_BYTES:
            raise DomainError("UPLOAD_TOO_LARGE", 413)
        payload = json.dumps(
            {"extension": extension, "content": base64.b64encode(content).decode()}
        )
        try:
            process = subprocess.run(
                [sys.executable, "-I", str(Path(__file__).resolve()), "--child"],
                input=payload.encode(),
                capture_output=True,
                timeout=TIMEOUT_SECONDS,
                check=False,
                env={"PATH": os.defpath, "LANG": "C.UTF-8"},
                cwd="/",
            )
        except subprocess.TimeoutExpired as exc:
            raise DomainError("DOCUMENT_PARSE_TIMEOUT", 422) from exc
        if process.returncode or len(process.stdout) > MAX_TEXT_BYTES * 8:
            raise DomainError("DOCUMENT_PARSE_FAILED", 422)
        try:
            result = json.loads(process.stdout)
        except (ValueError, UnicodeError) as exc:
            raise DomainError("DOCUMENT_PARSE_FAILED", 422) from exc
        if "error" in result:
            code = result["error"]
            raise DomainError(code, 415 if code == "UNSUPPORTED_DOCUMENT" else 422)
    return {
        **result,
        "original_hash": hashlib.sha256(content).hexdigest(),
        "media_type": MEDIA_TYPES[extension],
        "extension": extension,
    }


def _child():
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    if sys.platform == "linux":
        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))

    def no_network(*args, **kwargs):
        raise ExtractionError("DOCUMENT_NETWORK_FORBIDDEN")

    socket.socket.connect = no_network
    socket.socket.connect_ex = no_network
    socket.create_connection = no_network
    try:
        payload = sys.stdin.buffer.read(MAX_BINARY_BYTES * 2 + 1)
        if len(payload) > MAX_BINARY_BYTES * 2:
            raise ExtractionError("UPLOAD_TOO_LARGE")
        request = json.loads(payload)
        content = base64.b64decode(request["content"], validate=True)
        result = _extract(content, request["extension"])
    except ExtractionError as exc:
        result = {"error": str(exc)}
    except Exception:
        result = {"error": "INVALID_DOCUMENT"}
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    _child()
