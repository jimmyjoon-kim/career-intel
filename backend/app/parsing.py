import io

from fastapi import HTTPException


def file_to_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
            return "\n".join((p.extract_text() or "") for p in reader.pages).strip()
        except Exception:  # noqa: BLE001 — a damaged or encrypted PDF is a user error, not a server error
            raise HTTPException(422, "This PDF could not be read. Try saving it again or upload a DOCX.")
    if name.endswith(".docx"):
        import docx

        doc = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs).strip()
    if name.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="replace").strip()
    raise HTTPException(415, "Upload a PDF, DOCX, TXT or MD file")
