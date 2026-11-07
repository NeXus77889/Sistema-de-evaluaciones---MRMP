import re
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from docx import Document


class DocxImportError(ValueError):
    pass


_MAX_UNCOMPRESSED_SIZE = 50 * 1024 * 1024
_QUESTION_RE = re.compile(
    r"^\s*(?:(?:pregunta\s+)?\d{1,3}\s*[.)\-:]\s*)(.+)$",
    re.IGNORECASE,
)
_OPTION_RE = re.compile(
    r"^\s*(?:\(([A-L])\)|\[([A-L])\]|([A-L])[.)]|([A-L]):)\s*(.+)$",
    re.IGNORECASE,
)
_ANSWER_MARKER_RE = re.compile(r"^(?:\[x\]|☒|✓|\*)\s*", re.IGNORECASE)


def parse_docx_questions(uploaded_file):
    content = uploaded_file.read()
    try:
        with ZipFile(BytesIO(content)) as archive:
            if len(archive.infolist()) > 2000:
                raise DocxImportError("El documento contiene demasiados elementos internos.")
            if sum(item.file_size for item in archive.infolist()) > _MAX_UNCOMPRESSED_SIZE:
                raise DocxImportError("El contenido descomprimido del documento supera 50 MB.")
        document = Document(BytesIO(content))
    except DocxImportError:
        raise
    except BadZipFile as error:
        raise DocxImportError("El archivo no es un documento .docx válido.") from error
    except Exception as error:
        raise DocxImportError("No se pudo leer el documento Word.") from error

    parsed = []
    current = None

    def store_current():
        if current and current["options"]:
            parsed.append(current)

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue

        option_match = _OPTION_RE.match(text)
        if option_match and current:
            option_text = option_match.group(5).strip()
            marker_match = _ANSWER_MARKER_RE.match(option_text)
            marked = marker_match is not None or any(
                run.bold for run in paragraph.runs if run.text.strip()
            )
            if marker_match:
                option_text = option_text[marker_match.end():].strip()
            current["options"].append({"text": option_text, "marked": marked})
            continue

        question_match = _QUESTION_RE.match(text)
        if question_match:
            store_current()
            current = {"text": question_match.group(1).strip(), "options": []}
        elif current and current["options"]:
            store_current()
            current = {"text": text, "options": []}
        elif current:
            current["text"] = f"{current['text']} {text}".strip()
        else:
            current = {"text": text, "options": []}

    store_current()

    if not parsed:
        raise DocxImportError(
            "No se encontraron preguntas con alternativas. Usa opciones rotuladas A), B), C) o D)."
        )
    if len(parsed) > 100:
        raise DocxImportError("El documento supera el límite de 100 preguntas.")

    result = []
    for question in parsed:
        if not question["text"] or len(question["text"]) > 5000:
            raise DocxImportError("Cada pregunta debe tener texto de hasta 5000 caracteres.")
        options = question["options"]
        if not 2 <= len(options) <= 12:
            raise DocxImportError(
                "Cada pregunta debe tener entre 2 y 12 alternativas rotuladas A) a L)."
            )
        marked_indexes = [index for index, option in enumerate(options) if option["marked"]]
        correct_index = marked_indexes[0] if len(marked_indexes) == 1 else None
        clean_options = []
        for index, option in enumerate(options):
            option_text = option["text"].strip()
            if not option_text or len(option_text) > 1000:
                raise DocxImportError("Cada alternativa debe tener texto de hasta 1000 caracteres.")
            clean_options.append(
                {"text": option_text, "correct": index == correct_index}
            )
        result.append(
            {"text": question["text"], "points": "1", "options": clean_options}
        )
    return result