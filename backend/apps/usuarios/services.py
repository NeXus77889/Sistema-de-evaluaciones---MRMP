import csv
from io import StringIO
from pathlib import Path
import re
from typing import BinaryIO
import unicodedata

import xlrd
from django.db import transaction
from django.db.models import Q
from django.utils.crypto import get_random_string
from openpyxl import load_workbook

from apps.evaluaciones.models import AsignacionDocente, Curso, Materia

from .models import User


EXPECTED_COLUMNS = (
    "identificacion",
    "nombres",
    "apellidos",
    "email",
    "curso_codigo",
    "curso_nombre",
)


class NominaImportError(ValueError):
    pass


def _cell_text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _normalise_text(value):
    text = unicodedata.normalize("NFKD", _cell_text(value))
    return " ".join(text.encode("ascii", "ignore").decode().lower().split())


def _sanitize_sheet_name(value):
    text = unicodedata.normalize("NFKC", _cell_text(value))
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"[^\wº°]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


VALID_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/msexcel",
    "application/x-msexcel",
    "application/x-excel",
    "application/excel",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/csv",
    "text/plain",
    "application/octet-stream",
}


def _validate_mime(source: BinaryIO):
    content_type = getattr(source, "content_type", None)
    if content_type and content_type.lower() not in VALID_MIME_TYPES:
        raise NominaImportError(f"Tipo de archivo no permitido: {content_type}.")


def _read_sheets(source: BinaryIO, filename: str):
    _validate_mime(source)
    extension = Path(filename).suffix.lower()
    if hasattr(source, "seek"):
        try:
            source.seek(0)
        except Exception:
            pass
    content = source.read()
    if hasattr(source, "seek"):
        try:
            source.seek(0)
        except Exception:
            pass

    # Detección inteligente por cabeceras mágicas o extensión
    is_zip = content.startswith(b"PK\x03\x04")
    is_ole = content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")

    # Word .docx con tablas de nóminas
    if extension == ".docx" or (is_zip and extension not in (".xlsx", ".xlsm")):
        try:
            from docx import Document
            from io import BytesIO
            doc = Document(BytesIO(content))
            sheets = []
            for index, table in enumerate(doc.tables, start=1):
                sheet_rows = []
                seen_cells = set()
                for row in table.rows:
                    row_vals = []
                    for cell in row.cells:
                        if cell._tc in seen_cells:
                            continue
                        seen_cells.add(cell._tc)
                        row_vals.append(_cell_text(cell.text))
                    if any(row_vals):
                        sheet_rows.append(row_vals)
                if sheet_rows:
                    sheets.append((f"Tabla {index}", sheet_rows))
            if sheets:
                return sheets
        except Exception:
            pass

    # Excel moderno (.xlsx)
    if extension in (".xlsx", ".xlsm") or is_zip:
        try:
            from io import BytesIO
            workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
            try:
                return [
                    (sheet.title, list(sheet.iter_rows(values_only=True)))
                    for sheet in workbook.worksheets
                ]
            finally:
                workbook.close()
        except Exception as openpyxl_error:
            # Fallback a xlrd por si fue renombrado
            try:
                workbook = xlrd.open_workbook(file_contents=content, on_demand=True)
                try:
                    return [
                        (
                            sheet.name,
                            [sheet.row_values(index) for index in range(sheet.nrows)],
                        )
                        for sheet in workbook.sheets()
                    ]
                finally:
                    workbook.release_resources()
            except Exception:
                raise NominaImportError(f"No se pudo leer el archivo Excel (.xlsx): {openpyxl_error}")

    # Excel heredado (.xls)
    if extension == ".xls" or is_ole:
        try:
            workbook = xlrd.open_workbook(file_contents=content, on_demand=True)
            try:
                return [
                    (
                        sheet.name,
                        [sheet.row_values(index) for index in range(sheet.nrows)],
                    )
                    for sheet in workbook.sheets()
                ]
            finally:
                workbook.release_resources()
        except Exception as xlrd_error:
            # Fallback a openpyxl por si es en realidad un xlsx
            try:
                from io import BytesIO
                workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
                try:
                    return [
                        (sheet.title, list(sheet.iter_rows(values_only=True)))
                        for sheet in workbook.worksheets
                    ]
                finally:
                    workbook.close()
            except Exception:
                raise NominaImportError(f"No se pudo leer el archivo Excel (.xls): {xlrd_error}")

    raise NominaImportError("El archivo debe tener extensión .xlsx, .xls o contener tablas .docx.")


def _standard_records(rows):
    if not rows:
        return None

    aliases = {
        "identificacion": {
            "identificacion",
            "cedula",
            "cedula de estudiante",
            "cedula estudiante",
            "numero de cedula",
        },
        "nombres": {"nombres", "nombre", "nombres del estudiante"},
        "apellidos": {"apellidos", "apellidos del estudiante"},
        "email": {"email", "correo", "correo electronico"},
        "curso_codigo": {"curso codigo", "codigo curso", "codigo del curso"},
        "curso_nombre": {"curso nombre", "nombre curso", "curso", "curso y paralelo"},
    }
    header_index = None
    column_indexes = {}
    for row_index, row in enumerate(rows):
        normalized_header = [
            re.sub(r"[^a-z0-9]+", " ", _normalise_text(value)).strip()
            for value in row
        ]
        candidate_indexes = {
            column: next(
                (
                    index
                    for index, value in enumerate(normalized_header)
                    if value in column_aliases
                ),
                None,
            )
            for column, column_aliases in aliases.items()
        }
        if candidate_indexes["identificacion"] is not None and candidate_indexes["nombres"] is not None:
            header_index = row_index
            column_indexes = candidate_indexes
            break
    if header_index is None:
        return None

    if column_indexes["apellidos"] is None:
        return None
    if column_indexes["curso_nombre"] is None:
        return None
    records = []
    for row_number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        values = {}
        for column, index in column_indexes.items():
            values[column] = _cell_text(row[index] if index is not None and index < len(row) else "")
        if not any(values.values()):
            continue
        missing_values = [
            column
            for column in ("identificacion", "nombres", "apellidos", "curso_nombre")
            if not values[column]
        ]
        if missing_values:
            raise NominaImportError(
                f"Fila {row_number}: faltan valores en "
                + ", ".join(missing_values)
                + "."
            )
        course_name = _normalize_course_name(values["curso_nombre"])
        course_code = values["curso_codigo"]
        if not course_code:
            course_text, parallel = _split_parallel(course_name)
            course_code = _course_code(course_text, parallel)
        values["curso_nombre"] = course_name
        values["curso_codigo"] = course_code
        records.append((row_number, values))
    return records


def _header_value(rows, label):
    for row in rows:
        for column_index, cell in enumerate(row):
            match = re.search(rf"{label}\s*:\s*(.*)$", _cell_text(cell), re.IGNORECASE)
            if not match:
                continue
            value = match.group(1).strip()
            if value:
                return value
            for adjacent_cell in row[column_index + 1 :]:
                value = _cell_text(adjacent_cell)
                if value:
                    return value
    return ""


def _split_parallel(course_text):
    quoted_parallel = re.search(
        r"[\"'“”]\s*([A-Za-z0-9]+)\s*[\"'“”]\s*$", course_text
    )
    if quoted_parallel:
        return course_text[: quoted_parallel.start()].strip(), quoted_parallel.group(1)

    plain_parallel = re.match(r"^(.*\S)\s+([A-Za-z])$", course_text)
    if plain_parallel:
        return plain_parallel.group(1).strip(), plain_parallel.group(2)
    return course_text.strip(), ""


def _normalize_course_name(value, parallel=""):
    from apps.evaluaciones.academic import format_course_name

    text = _sanitize_sheet_name(value)
    text = re.sub(r"\s+", " ", text).strip(" .\t")
    course_text, embedded_parallel = _split_parallel(text)
    parallel = (parallel or embedded_parallel or "A").upper()
    return format_course_name(f"{course_text} {parallel}".strip())


def _course_code(course_text, parallel):
    parts = []
    grade = re.match(r"^\s*(\d+)\s*(?:º|°|o|do|to)?\s*", course_text, re.IGNORECASE)
    if grade:
        parts.append(grade.group(1))
        course_text = course_text[grade.end() :]

    ignored_words = {"de", "del", "la", "las", "el", "los", "y"}
    course_words = re.findall(r"[a-z0-9]+", _normalise_text(course_text))
    parts.extend(word[:4].upper() for word in course_words if word not in ignored_words)
    parallel_words = re.findall(r"[a-z0-9]+", _normalise_text(parallel))
    parts.extend(word[:4].upper() for word in parallel_words)
    if not parts:
        raise NominaImportError("No se pudo determinar el código del curso.")
    return "-".join(parts)[:20].rstrip("-")


def _institutional_records(sheet_name, rows):
    header_index = None
    name_index = None
    identification_index = None
    email_index = None
    for row_index, row in enumerate(rows):
        header = [_normalise_text(value) for value in row]
        name_index = next(
            (
                index
                for index, value in enumerate(header)
                if any(label in value for label in ("nomina de estudiante", "nombre completo", "nombres y apellidos"))
            ),
            None,
        )
        identification_index = next(
            (
                index
                for index, value in enumerate(header)
                if "cedula" in value or "identificacion" in value
            ),
            None,
        )
        if name_index is not None and identification_index is not None:
            header_index = row_index
            email_index = next(
                (
                    index
                    for index, value in enumerate(header)
                    if "email" in value or "correo electronico" in value or "correo" in value
                ),
                None,
            )
            break

    if header_index is None:
        return None

    clean_sheet_name = _sanitize_sheet_name(sheet_name)
    tab_course, tab_parallel = _split_parallel(clean_sheet_name)
    course_text = _header_value(rows, "Curso") or tab_course or clean_sheet_name
    course_text, embedded_parallel = _split_parallel(course_text)
    parallel = _header_value(rows, "Paralelo") or embedded_parallel or tab_parallel or "A"
    course_name = _normalize_course_name(
        course_text or tab_course or sheet_name,
        parallel,
    )
    course_code = _course_code(course_text or tab_course or sheet_name, parallel)

    records = []
    for row_index, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        raw_name = _cell_text(row[name_index] if name_index < len(row) else "")
        raw_identification = _cell_text(
            row[identification_index] if identification_index < len(row) else ""
        )
        if not raw_name or not raw_identification:
            continue

        identification = re.sub(r"\D", "", raw_identification)
        if not identification:
            continue
        if len(identification) == 9:
            identification = "0" + identification

        name_parts = raw_name.split()
        if len(name_parts) < 3:
            raise NominaImportError(
                f"Hoja '{sheet_name}', fila {row_index}: "
                "la nómina debe incluir dos apellidos y al menos un nombre."
            )
        email = _cell_text(row[email_index]) if email_index is not None and email_index < len(row) else ""
        records.append(
            (
                f"Hoja '{sheet_name}', fila {row_index}",
                {
                    "identificacion": identification,
                    "nombres": " ".join(name_parts[2:]),
                    "apellidos": " ".join(name_parts[:2]),
                    "email": email,
                    "curso_codigo": course_code,
                    "curso_nombre": course_name,
                },
            )
        )
    return records


def _empty_summary():
    return {
        "filas": 0,
        "estudiantes_creados": 0,
        "estudiantes_actualizados": 0,
        "cursos_creados": 0,
        "cursos_actualizados": 0,
        "docentes_creados": 0,
        "docentes_actualizados": 0,
        "asignaciones": 0,
        "claves_temporales": [],
        "reporte": [],
    }


def _read_teacher_sheets(source: BinaryIO, filename: str):
    _validate_mime(source)
    extension = Path(filename).suffix.lower()
    if hasattr(source, "seek"):
        try:
            source.seek(0)
        except Exception:
            pass
    content = source.read()
    if hasattr(source, "seek"):
        try:
            source.seek(0)
        except Exception:
            pass

    if extension == ".xlsx" or content.startswith(b"PK\x03\x04"):
        from io import BytesIO
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
        try:
            return [
                (sheet.title, list(sheet.iter_rows(values_only=True)))
                for sheet in workbook.worksheets
            ]
        finally:
            workbook.close()
    if extension == ".xls" or content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        workbook = xlrd.open_workbook(file_contents=content, on_demand=True)
        try:
            return [
                (
                    sheet.name,
                    [sheet.row_values(index) for index in range(sheet.nrows)],
                )
                for sheet in workbook.sheets()
            ]
        finally:
            workbook.release_resources()
    if extension == ".csv":
        encodings = ["utf-8-sig", "utf-8", "cp1252", "latin-1", "iso-8859-1"]
        text = None
        for enc in encodings:
            try:
                text = content.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            text = content.decode("latin-1", errors="replace")
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        return [(Path(filename).stem, list(csv.reader(StringIO(text), dialect)))]
    raise NominaImportError("El archivo de docentes debe ser .xlsx, .xls o .csv.")


def _teacher_records(sheet_name, rows):
    header_index = None
    indexes = {}
    aliases = {
        "identificacion": {"cedula", "identificacion"},
        "apellidos": {"apellidos", "apellido"},
        "nombres": {"nombres", "nombre"},
        "email": {"email", "correo", "correo electronico"},
        "materias": {"materias", "materia", "materia(s)"},
        "cursos": {"cursos", "curso", "curso(s)"},
    }
    for row_index, row in enumerate(rows):
        normalized = [_normalise_text(value).strip(" :") for value in row]
        indexes = {
            field: next(
                (index for index, value in enumerate(normalized) if value in names),
                None,
            )
            for field, names in aliases.items()
        }
        if all(index is not None for index in indexes.values()):
            header_index = row_index
            break
    if header_index is None:
        return None

    records = []
    for row_index, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        values = {
            field: _cell_text(row[index] if index < len(row) else "")
            for field, index in indexes.items()
        }
        if not any(values.values()):
            continue
        missing = [field for field in aliases if not values[field]]
        if missing:
            raise NominaImportError(
                f"Hoja '{sheet_name}', fila {row_index}: faltan "
                + ", ".join(missing)
                + "."
            )
        records.append((f"Hoja '{sheet_name}', fila {row_index}", values))
    return records


def _split_values(value):
    return [part.strip() for part in re.split(r"[,;|\n]+", value) if part.strip()]


def _resolve_subject(value):
    normalized = _normalise_text(value)
    for subject in Materia.objects.all():
        if normalized in {_normalise_text(subject.nombre), _normalise_text(subject.codigo)}:
            return subject
    raise NominaImportError(f"No existe la materia '{value}'.")


def _resolve_course(value):
    from apps.evaluaciones.academic import format_course_name

    normalized = _normalise_text(value)
    standardized = format_course_name(value)
    norm_standardized = _normalise_text(standardized)

    courses = list(Curso.objects.all())
    for course in courses:
        course_norm = _normalise_text(course.nombre)
        course_str_norm = _normalise_text(str(course))
        course_code_norm = _normalise_text(course.codigo)
        if (
            normalized in {course_norm, course_str_norm, course_code_norm}
            or norm_standardized in {course_norm, course_str_norm, course_code_norm}
        ):
            return course

    course_name, parallel = _split_parallel(value)
    parallel = parallel or "A"
    try:
        code = _course_code(course_name, parallel)
    except NominaImportError:
        code = ""
    for course in courses:
        if code and _normalise_text(course.codigo) == _normalise_text(code):
            return course
    raise NominaImportError(f"No existe el curso '{value}'.")


def _assignment_pairs(subjects, courses, row_label):
    if len(subjects) == 1:
        return [(subjects[0], course) for course in courses]
    if len(courses) == 1:
        return [(subject, courses[0]) for subject in subjects]
    if len(subjects) == len(courses):
        return list(zip(subjects, courses))
    raise NominaImportError(
        f"{row_label}: la cantidad de materias y cursos no permite "
        "determinar las asignaciones; use una materia, un curso o listas de igual longitud."
    )


@transaction.atomic
def importar_nomina(source: BinaryIO, filename: str):
    try:
        sheets = _read_sheets(source, filename)
    except NominaImportError:
        raise
    except Exception as error:
        raise NominaImportError(f"No se pudo leer el archivo Excel: {error}") from error

    records = []
    for sheet_name, rows in sheets:
        sheet_records = _institutional_records(sheet_name, rows)
        if sheet_records is None:
            sheet_records = _standard_records(rows)
        if sheet_records:
            records.extend(sheet_records)
    if not records:
        raise NominaImportError("No se encontraron filas de estudiantes en el archivo.")

    summary = _empty_summary()

    for row_number, record in records:
        try:
            curso = Curso.objects.filter(codigo=record["curso_codigo"]).first()
            if curso is None:
                curso = Curso.objects.filter(nombre__iexact=record["curso_nombre"]).first()
            curso_created = curso is None
            if curso_created:
                curso = Curso.objects.create(
                    codigo=record["curso_codigo"],
                    nombre=record["curso_nombre"],
                )
            if curso_created:
                summary["cursos_creados"] += 1
            elif curso.nombre != record["curso_nombre"]:
                curso.nombre = record["curso_nombre"]
                curso.save(update_fields=["nombre"])
                summary["cursos_actualizados"] += 1

            student = User.objects.select_for_update().filter(
                Q(identification=record["identificacion"])
                | Q(username=record["identificacion"])
            ).first()
            temporary_password = get_random_string(20)
            if student is None:
                student = User.objects.create_user(
                    username=record["identificacion"],
                    email=record["email"]
                    or f"estudiante-{record['identificacion']}@nomina.invalid",
                    password=temporary_password,
                    first_name=record["nombres"],
                    last_name=record["apellidos"],
                    rol=User.Role.STUDENT,
                    identification=record["identificacion"],
                    debe_cambiar_password=True,
                )
                summary["estudiantes_creados"] += 1
            else:
                student.username = record["identificacion"]
                student.first_name = record["nombres"]
                student.last_name = record["apellidos"]
                if record["email"]:
                    student.email = record["email"]
                student.identification = record["identificacion"]
                student.rol = User.Role.STUDENT
                update_fields = [
                    "username",
                    "first_name",
                    "last_name",
                    "identification",
                    "rol",
                ]
                if record["email"]:
                    update_fields.append("email")
                student.set_password(temporary_password)
                student.debe_cambiar_password = True
                update_fields.extend(("password", "debe_cambiar_password"))
                student.save(update_fields=update_fields)
                summary["estudiantes_actualizados"] += 1

            previous_courses = student.cursos.exclude(pk=curso.pk)
            for previous_course in previous_courses:
                previous_course.estudiantes.remove(student)
            curso.estudiantes.add(student)
            summary["filas"] += 1
            summary["claves_temporales"].append(
                (record["identificacion"], temporary_password)
            )
            summary["reporte"].append(
                {
                    "identificacion": record["identificacion"],
                    "username": student.username,
                    "nombres": record["nombres"],
                    "apellidos": record["apellidos"],
                    "rol": "Estudiante",
                    "curso": curso.nombre,
                    "clave_temporal": temporary_password,
                }
            )
        except Exception as error:
            raise NominaImportError(f"Fila {row_number}: {error}") from error

    return summary


@transaction.atomic
def importar_docentes(source: BinaryIO, filename: str):
    try:
        sheets = _read_teacher_sheets(source, filename)
    except NominaImportError:
        raise
    except Exception as error:
        raise NominaImportError(f"No se pudo leer el archivo de docentes: {error}") from error

    records = []
    for sheet_name, rows in sheets:
        sheet_records = _teacher_records(sheet_name, rows)
        if sheet_records:
            records.extend(sheet_records)
    if not records:
        raise NominaImportError("No se encontraron docentes en el archivo.")

    summary = _empty_summary()
    imported_teachers = {}
    for row_label, record in records:
        try:
            identification = re.sub(r"\D", "", record["identificacion"])
            if len(identification) == 9:
                identification = "0" + identification
            if not identification:
                raise NominaImportError("la cédula no contiene dígitos.")
            if "@" not in record["email"]:
                raise NominaImportError("el correo no es válido.")

            subjects = [_resolve_subject(value) for value in _split_values(record["materias"])]
            courses = [_resolve_course(value) for value in _split_values(record["cursos"])]
            assignment_pairs = _assignment_pairs(subjects, courses, row_label)

            imported_teacher = imported_teachers.get(identification)
            if imported_teacher:
                teacher = imported_teacher["teacher"]
                temporary_password = imported_teacher["password"]
            else:
                teacher = User.objects.select_for_update().filter(
                    Q(identification=identification) | Q(username=identification)
                ).first()
                temporary_password = get_random_string(20)
                if teacher is None:
                    teacher = User.objects.create_user(
                        username=identification,
                        email=record["email"],
                        password=temporary_password,
                        first_name=record["nombres"],
                        last_name=record["apellidos"],
                        rol=User.Role.TEACHER,
                        identification=identification,
                        debe_cambiar_password=True,
                    )
                    summary["docentes_creados"] += 1
                else:
                    teacher.username = identification
                    teacher.first_name = record["nombres"]
                    teacher.last_name = record["apellidos"]
                    teacher.email = record["email"]
                    teacher.identification = identification
                    teacher.rol = User.Role.TEACHER
                    teacher.set_password(temporary_password)
                    teacher.debe_cambiar_password = True
                    teacher.save(
                        update_fields=(
                            "first_name",
                            "last_name",
                            "username",
                            "email",
                            "identification",
                            "rol",
                            "password",
                            "debe_cambiar_password",
                        )
                    )
                    summary["docentes_actualizados"] += 1
                imported_teacher = {
                    "teacher": teacher,
                    "password": temporary_password,
                    "report": {
                        "identificacion": identification,
                        "username": teacher.username,
                        "nombres": record["nombres"],
                        "apellidos": record["apellidos"],
                        "rol": "Docente",
                        "curso": "",
                        "clave_temporal": temporary_password,
                    },
                    "courses": [],
                }
                imported_teachers[identification] = imported_teacher
                summary["claves_temporales"].append(
                    (identification, temporary_password)
                )
                summary["reporte"].append(imported_teacher["report"])

            for subject, course in assignment_pairs:
                assignment, created = AsignacionDocente.objects.get_or_create(
                    docente=teacher,
                    materia=subject,
                    curso=course,
                    defaults={"activo": True},
                )
                if not created and not assignment.activo:
                    assignment.activo = True
                    assignment.save(update_fields=["activo"])
                summary["asignaciones"] += 1

            summary["filas"] += 1
            for course in courses:
                if course.nombre not in imported_teacher["courses"]:
                    imported_teacher["courses"].append(course.nombre)
            imported_teacher["report"]["curso"] = ", ".join(
                imported_teacher["courses"]
            )
        except Exception as error:
            raise NominaImportError(f"{row_label}: {error}") from error

    return summary