"""Reglas para interpretar la plantilla de personal institucional (UEPMRMP).

Este módulo no depende de Django: solo interpreta filas de la hoja y decide
rol, nombres y apellidos. El acceso a la base de datos está en
``services.importar_personal``.

Para ajustar quién es administrativo o docente, edita las tres tuplas
``FUNCIONES_*`` de abajo (se escriben sin tildes y en minúsculas; cada palabra
coincide con el *inicio* de una palabra de la función, así "administrador"
también cubre "administradora").
"""

import re
import unicodedata

# Valores iguales a los de ``User.Role``.
ROL_ADMIN = "ADMIN"
ROL_DOCENTE = "DOCENTE"

# Cargos que reciben el rol Administrador en el sistema. Ese rol ve el panel
# general con todas las evaluaciones, resultados e incidentes.
FUNCIONES_ADMINISTRATIVAS = (
    "rector",
    "administrador",
    "administrativ",
    "secretari",
    "inspector",
    "subinspector",
    "coord",
    "camara",
)

# De los cargos anteriores, los que además reciben ``is_staff`` (acceso al
# panel de administración de Django y a la atención de tickets de clave).
FUNCIONES_CON_ACCESO_STAFF = (
    "rector",
    "administrador",
    "secretari",
)

# Funciones que identifican a un docente además de las tutorías por curso
# ("3° A", "1ero", "Inicial 2") y de tener una asignatura en la hoja.
FUNCIONES_DOCENTES = (
    "docente",
    "tutor",
    "informatica",
    "robotica",
    "matematica",
    "fisica",
    "quimica",
    "biologia",
    "lengua",
    "ingles",
    "historia",
    "educacion",
    "musica",
    "arte",
)

TITULOS = {
    "abg", "arq", "dr", "dra", "econ", "hna", "hno", "ing", "lcda", "lcdo",
    "lic", "mg", "mgs", "msc", "mtr", "mtra", "phd", "prof", "profe", "psc",
    "psic", "sr", "sra", "srta", "tlga", "tlgo", "tnlga", "tnlgo",
}

PARTICULAS = {"de", "del", "la", "las", "los", "y", "san", "santa"}

COLUMNAS = {
    "cedula": {"cedula", "identificacion"},
    "nombre": {"nombre", "nombres", "nombre completo", "apellidos y nombres"},
    "correo": {"correo", "email", "correo electronico", "correo institucional"},
    "funcion": {"funcion tutoria", "funcion", "cargo"},
    "asignatura": {"asignatura", "materia"},
    "curso": {"curso paralelo", "curso", "cursos"},
}
COLUMNAS_OBLIGATORIAS = ("cedula", "nombre", "funcion")


def cell_text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def normalise(value):
    text = unicodedata.normalize("NFKD", cell_text(value))
    text = text.encode("ascii", "ignore").decode().lower().replace("_", " ")
    return " ".join(text.split())


def _bare(token):
    return normalise(token).strip(".,;:")


def _has_keyword(text, keywords):
    return any(re.search(r"\b" + re.escape(word), text) for word in keywords)


def classify_function(funcion, asignatura=""):
    """Devuelve ``(rol, es_staff)``; ``(None, False)`` si no se reconoce."""
    text = normalise(funcion)
    if _has_keyword(text, FUNCIONES_ADMINISTRATIVAS):
        return ROL_ADMIN, _has_keyword(text, FUNCIONES_CON_ACCESO_STAFF)
    if (
        re.match(r"^(inicial|\d)", text)
        or _has_keyword(text, FUNCIONES_DOCENTES)
        or cell_text(asignatura)
    ):
        return ROL_DOCENTE, False
    return None, False


def split_name(full_name):
    """Quita títulos ("Lcda.", "MSc.") y separa ``(nombres, apellidos)``.

    La plantilla trae "título + nombres + apellidos": los dos últimos
    apellidos van al final (con partículas como "De la").
    """
    tokens = cell_text(full_name).split()
    while tokens and _bare(tokens[0]) in TITULOS:
        tokens.pop(0)
    if not tokens:
        return "", ""
    if len(tokens) == 1:
        return tokens[0], ""
    if len(tokens) == 2:
        return tokens[0], tokens[1]
    index = len(tokens)
    found = 0
    while found < 2 and index > 1:
        index -= 1
        while index > 1 and _bare(tokens[index - 1]) in PARTICULAS:
            index -= 1
        found += 1
    return " ".join(tokens[:index]), " ".join(tokens[index:])


def normalise_cedula(value):
    digits = re.sub(r"\D", "", cell_text(value))
    if len(digits) == 9:
        digits = "0" + digits
    return digits


def parse_sheet(sheet_name, rows):
    """Lee una hoja de la plantilla. ``None`` si la hoja no tiene los encabezados."""
    header_index = None
    indexes = {}
    for row_index, row in enumerate(rows):
        normalised = [normalise(value) for value in row]
        found = {
            field: next(
                (i for i, value in enumerate(normalised) if value in names), None
            )
            for field, names in COLUMNAS.items()
        }
        if all(found[field] is not None for field in COLUMNAS_OBLIGATORIAS):
            header_index = row_index
            indexes = found
            break
    if header_index is None:
        return None

    def value(row, field):
        index = indexes.get(field)
        return cell_text(row[index]) if index is not None and index < len(row) else ""

    records = []
    for row_index, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        cedula_raw = value(row, "cedula")
        nombre = value(row, "nombre")
        if not cedula_raw and not nombre:
            continue
        records.append(
            (
                f"Hoja '{sheet_name}', fila {row_index}",
                {
                    "identificacion": normalise_cedula(cedula_raw),
                    "nombre": nombre,
                    "correo": value(row, "correo"),
                    "funcion": value(row, "funcion"),
                    "asignatura": value(row, "asignatura"),
                    "curso": value(row, "curso"),
                },
            )
        )
    return records
