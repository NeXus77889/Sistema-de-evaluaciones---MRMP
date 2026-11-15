import re
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


class DocxImportError(ValueError):
    pass


_MAX_UNCOMPRESSED_SIZE = 50 * 1024 * 1024
_QUESTION_RE = re.compile(
    r"^\s*(?:(?:pregunta|item|reactivo)\s+)?\d{1,3}\s*[.)\-:]\s*(.+)$",
    re.IGNORECASE,
)
_OPTION_RE = re.compile(
    r"^\s*(?:\(([A-La-l])\)|\[([A-La-l])\]|([A-La-l])[.)\-:]|([A-La-l]):)\s*(.+)$",
    re.IGNORECASE,
)
_ANSWER_START_MARKER_RE = re.compile(r"^(?:\[x\]|\[X\]|\(x\)|\(X\)|☒|☑|✓|\*)\s*", re.IGNORECASE)
_ANSWER_END_MARKER_RE = re.compile(r"\s*(?:\[x\]|\[X\]|\(x\)|\(X\)|☒|☑|✓|\*)\s*$", re.IGNORECASE)


def _iter_document_paragraphs(document):
    """
    Extrae todos los párrafos del documento (incluyendo tablas y celdas)
    preservando el orden secuencial del cuerpo del documento,
    e ignorando de forma segura runs colgados, celdas fusionadas duplicadas y formatos nulos.
    """
    for child in document.element.body:
        if child.tag.endswith("p"):
            yield Paragraph(child, document)
        elif child.tag.endswith("tbl"):
            tbl = Table(child, document)
            seen_cells = set()
            for row in tbl.rows:
                for cell in row.cells:
                    if cell._tc in seen_cells:
                        continue
                    seen_cells.add(cell._tc)
                    for paragraph in cell.paragraphs:
                        yield paragraph


def parse_docx_questions(uploaded_file):
    content = uploaded_file.read() if hasattr(uploaded_file, "read") else uploaded_file
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
        raise DocxImportError(f"No se pudo leer el documento Word: {error}") from error

    parsed = []
    current = None

    def store_current():
        if current and current["options"]:
            parsed.append(current)

    for paragraph in _iter_document_paragraphs(document):
        try:
            raw_text = paragraph.text
        except (AttributeError, ValueError):
            continue

        if not raw_text:
            continue
        text = re.sub(r"[\xa0\s]+", " ", str(raw_text)).strip()
        if not text:
            continue

        # Detección de opción de respuesta
        option_match = _OPTION_RE.match(text)
        if option_match and current:
            # Obtener el texto de la alternativa (grupo 5)
            option_text = option_match.group(5).strip()
            start_marker = _ANSWER_START_MARKER_RE.match(option_text)
            end_marker = _ANSWER_END_MARKER_RE.search(option_text)
            marked = start_marker is not None or end_marker is not None

            if not marked:
                # Comprobar formato en negrita de runs de forma segura
                try:
                    marked = any(
                        getattr(run, "bold", False)
                        for run in getattr(paragraph, "runs", [])
                        if run and getattr(run, "text", "") and str(run.text).strip()
                    )
                except (AttributeError, ValueError):
                    marked = False

            if start_marker:
                option_text = option_text[start_marker.end():].strip()
            if end_marker:
                option_text = option_text[:end_marker.start()].strip()

            current["options"].append({"text": option_text, "marked": marked})
            continue

        # Detección de pregunta
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
