import re
import unicodedata


LEVELS = (
    ("initial", "Inicial"),
    ("elementary", "Básica elemental"),
    ("middle", "Básica media"),
    ("upper", "Básica superior"),
    ("baccalaureate", "Bachillerato BGU / Técnico"),
    ("other", "Otros cursos"),
)
LEVEL_LABELS = dict(LEVELS)
DASHBOARD_LEVEL_LABELS = {
    "initial": "Inicial",
    "elementary": "Básica Elemental",
    "middle": "Básica Media",
    "upper": "Básica Superior",
    "baccalaureate": "Bachillerato BGU / Técnico",
    "other": "Otros cursos",
}
_ORDINALS = {
    "primero": 1,
    "primera": 1,
    "segundo": 2,
    "segunda": 2,
    "tercero": 3,
    "tercera": 3,
    "cuarto": 4,
    "cuarta": 4,
    "quinto": 5,
    "quinta": 5,
    "sexto": 6,
    "sexta": 6,
    "septimo": 7,
    "septima": 7,
    "octavo": 8,
    "octava": 8,
    "noveno": 9,
    "novena": 9,
    "decimo": 10,
    "decima": 10,
}
_EXTENDED_ORDINALS = {
    **_ORDINALS,
    "primer": 1,
    "tercer": 3,
}


def _normalized(value):
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", value).strip().lower()


def format_course_name(course_or_name, code=""):
    """
    Estandariza los nombres y representaciones de cursos según las normas institucionales
    de la Unidad Educativa Particular Monseñor Roberto María del Pozo:
    - Prohibido usar frases descriptivas largas ("tercer curso de informática", "tercer curso de ciencias").
    - Formato estandarizado institucional obligatorio: "3º BGU [Especialidad] [Paralelo]".
    - Si un paralelo no tiene especificación B (o C/D), asigna automáticamente la letra 'A'.
    """
    if hasattr(course_or_name, "nombre"):
        raw_name = getattr(course_or_name, "nombre", "")
        code = getattr(course_or_name, "codigo", "") or code
    else:
        raw_name = str(course_or_name or "")

    text = raw_name.strip()
    if not text:
        return ""

    norm = _normalized(f"{text} {code}".strip())
    n_text = _normalized(text)
    n_code = _normalized(code)

    # Inicial
    if "inicial" in norm:
        match_init = re.search(r"\b(1|2)\b", norm)
        return f"Inicial {match_init.group(1)}" if match_init else "Inicial"

    # Paralelo: busca explícitamente en el texto primero, luego en el código
    parallel = None
    par_match = re.search(r"\bparalelo\s*([a-z0-9])\b", n_text)
    if not par_match:
        par_match = re.search(r"[\s\-_]([a-z])\s*$", n_text)
    if par_match:
        parallel = par_match.group(1).upper()
    elif code:
        par_match_code = re.search(r"\bparalelo\s*([a-z0-9])\b", n_code)
        if not par_match_code:
            par_match_code = re.search(r"[\s\-_]([a-z])\s*$", n_code)
        if par_match_code:
            parallel = par_match_code.group(1).upper()

    if not parallel or parallel not in ("A", "B", "C", "D", "E", "F"):
        parallel = "A"

    # Grado
    grade = None
    for word, g in _EXTENDED_ORDINALS.items():
        if re.search(rf"\b{word}\b", norm):
            grade = g
            break
    if grade is None:
        gm = re.search(r"\b(10|[1-9])\s*(?:º|°|o|ro|do|to|ero)?\b", norm)
        if gm:
            grade = int(gm.group(1))

    # Especialidad
    specialty = None
    if re.search(r"\b(inf|informatica|sistemas|computacion|programacion)\b", norm):
        specialty = "Informática"
    elif re.search(r"\b(cien|ciencias)\b", norm):
        specialty = "Ciencias"
    elif re.search(r"\b(cont|contabilidad)\b", norm):
        specialty = "Contabilidad"

    is_bach = (
        bool(re.search(r"\b(bgu|bachillerato|curso|tecnico)\b", norm))
        or (grade is not None and grade <= 3 and specialty is not None)
    )

    if is_bach and grade is not None:
        spec_str = f" {specialty}" if specialty else ""
        return f"{grade}º BGU{spec_str} {parallel}".strip()
    elif specialty and grade is not None:
        return f"{grade}º BGU {specialty} {parallel}"
    elif grade is not None:
        if any(term in norm for term in ("egb", "grado", "basica")):
            return f"{grade}º EGB {parallel}"
        return f"{grade}º {parallel}"

    return text


def _grade(course):
    text = _normalized(f"{course.nombre} {course.codigo}")
    for word, grade in _ORDINALS.items():
        if re.search(rf"\b{word}\b", text):
            return grade
    match = re.search(r"\b(10|[1-9])\s*(?:º|°|o|ro|do|to|ero)?\b", text)
    return int(match.group(1)) if match else None


def course_level(course):
    text = _normalized(f"{course.nombre} {course.codigo}")
    if re.search(r"\b(inicial|prebasica|prebasico)\b", text):
        return "initial"

    grade = _grade(course)
    has_egb = "egb" in text
    has_baccalaureate = any(
        term in text
        for term in ("bgu", "bachillerato", "tecnico", "ciencias", "informatica", "contabilidad")
    )
    if has_egb and grade:
        return "elementary" if grade <= 4 else "middle" if grade <= 7 else "upper"
    if grade and grade <= 10:
        if grade >= 8:
            return "upper"
        if has_baccalaureate and grade <= 3:
            return "baccalaureate"
        if grade <= 4:
            return "elementary"
        return "middle"
    if has_baccalaureate:
        return "baccalaureate"
    return "other"


def course_sort_key(course):
    level = course_level(course)
    level_order = next(index for index, (key, _) in enumerate(LEVELS) if key == level)
    grade = _grade(course)
    specialty_order = 0
    if level == "baccalaureate":
        text = _normalized(course.nombre)
        specialty_order = next(
            (
                index
                for index, term in enumerate(("ciencias", "contabilidad", "informatica"))
                if term in text
            ),
            3,
        )
    return (
        level_order,
        specialty_order,
        grade if grade is not None else 99,
        _normalized(course.nombre),
        _normalized(course.codigo),
    )


def grouped_course_choices(courses):
    grouped = {}
    for course in sorted(courses, key=course_sort_key):
        level = course_level(course)
        label = LEVEL_LABELS[level]
        if level == "baccalaureate":
            text = _normalized(course.nombre)
            specialty = next(
                (
                    name
                    for term, name in (
                        ("ciencias", "Ciencias"),
                        ("informatica", "Informática"),
                        ("contabilidad", "Contabilidad"),
                    )
                    if term in text
                ),
                "General / Técnico",
            )
            label = f"{label} · {specialty}"
        grouped.setdefault(label, []).append((course.pk, format_course_name(course)))
    return [(label, choices) for label, choices in grouped.items()]


def group_items_by_level(items, exam_getter=lambda item: item):
    grouped = {key: [] for key in DASHBOARD_LEVEL_LABELS}
    for item in items:
        exam = exam_getter(item)
        courses = list(exam.cursos.all())
        if exam.curso_id and all(course.pk != exam.curso_id for course in courses):
            courses.append(exam.curso)
        course = min(courses, key=course_sort_key) if courses else None
        level = course_level(course) if course else "other"
        grouped[level].append(item)
    return [
        {"key": key, "label": DASHBOARD_LEVEL_LABELS[key], "items": grouped[key]}
        for key in DASHBOARD_LEVEL_LABELS
        if grouped[key]
    ]


def format_action_repr(repr_str):
    """
    Estandariza textos de representación en logs y acciones:
    Ej: 'Juanito farralas - matemática - Segundo Curso Informática - Paralelo A'
    ->  'Juanito farralas - matemática - 2º BGU Informática A'
    """
    if not repr_str:
        return ""
    parts = str(repr_str).split(" - ")
    if len(parts) >= 3:
        # Check course in the last segment (or last two segments if "Paralelo A" was separated)
        combined_last = " ".join(parts[2:])
        fmt_combined = format_course_name(combined_last)
        if fmt_combined and fmt_combined != combined_last:
            return f"{parts[0]} - {parts[1]} - {fmt_combined}"
        parts[-1] = format_course_name(parts[-1])
        return " - ".join(parts)
    return format_course_name(repr_str)
