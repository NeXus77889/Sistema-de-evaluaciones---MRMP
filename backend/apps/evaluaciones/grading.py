from decimal import Decimal, ROUND_HALF_UP

from apps.evaluaciones.grading_config import PESO_EXAMEN_FINAL
from apps.evaluaciones.models import Curso, InsumoCalificacion, RegistroCalificacion


ONLINE_EVALUATION_NAME = "Evaluación en línea"
METACOGNITION_NAME = "Metacognitiva"
PHYSICAL_ASSESSMENT_NAME = "Aporte / Examen presencial"
FINAL_EXAM_NAME = "Examen Final Institucional"
ONLINE_EVALUATION_WEIGHT = Decimal("20.00")
METACOGNITION_WEIGHT = Decimal("20.00")
PHYSICAL_ASSESSMENT_WEIGHT = Decimal("20.00")


def _save_insumo(insumo, *, name, kind, weight, trimester, partial):
    period = f"Trimestre {trimester} - Parcial {partial}"
    updates = []
    for field, value in (
        ("nombre", name),
        ("tipo", kind),
        ("ponderacion", weight),
        ("trimestre", trimester),
        ("parcial", partial),
        ("periodo", period),
    ):
        if getattr(insumo, field) != value:
            setattr(insumo, field, value)
            updates.append(field)
    if updates:
        insumo.save(update_fields=updates)
    return insumo


def _ensure_insumo(curso, materia, docente, *, name, kind, weight, trimester, partial, reuse_types=()):
    base = InsumoCalificacion.objects.filter(
        curso=curso,
        materia=materia,
        trimestre=trimester,
        parcial=partial,
        tarea__isnull=True,
    )
    insumo = base.filter(nombre=name).first()
    if insumo is None and reuse_types:
        insumo = base.filter(tipo__in=reuse_types).order_by("created_at", "pk").first()
    if insumo is None:
        insumo = InsumoCalificacion.objects.create(
            curso=curso,
            materia=materia,
            docente=docente,
            nombre=name,
            tipo=kind,
            trimestre=trimester,
            parcial=partial,
            periodo=f"Trimestre {trimester} - Parcial {partial}",
            ponderacion=weight,
        )
    else:
        insumo = _save_insumo(
            insumo,
            name=name,
            kind=kind,
            weight=weight,
            trimester=trimester,
            partial=partial,
        )
    return insumo


def normalize_misplaced_final_insumos(curso, materia):
    """Keep historical "final" inputs in their actual partial category."""
    misplaced = InsumoCalificacion.objects.filter(
        curso=curso,
        materia=materia,
        tipo=InsumoCalificacion.TIPO_EXAMEN_FINAL,
        tarea__isnull=True,
    ).order_by("trimestre", "parcial", "created_at", "pk")
    handled = set()
    for insumo in misplaced:
        key = (insumo.trimestre, insumo.parcial)
        if key == (3, 2):
            target_name = FINAL_EXAM_NAME
            target_kind = InsumoCalificacion.TIPO_EXAMEN_FINAL
            target_weight = PESO_EXAMEN_FINAL
        elif insumo.parcial == 1:
            target_name = ONLINE_EVALUATION_NAME
            target_kind = InsumoCalificacion.TIPO_EVALUACION
            target_weight = ONLINE_EVALUATION_WEIGHT
        else:
            target_name = PHYSICAL_ASSESSMENT_NAME
            target_kind = InsumoCalificacion.TIPO_INSUMO_2
            target_weight = PHYSICAL_ASSESSMENT_WEIGHT
        already_has_required = InsumoCalificacion.objects.filter(
            curso=curso,
            materia=materia,
            trimestre=insumo.trimestre,
            parcial=insumo.parcial,
            nombre=target_name,
            tipo=target_kind,
        ).exclude(pk=insumo.pk).exists()
        if key in handled or already_has_required:
            _save_insumo(
                insumo,
                name=f"Insumo anterior: {insumo.nombre}",
                kind=InsumoCalificacion.TIPO_INSUMO_1,
                weight=insumo.ponderacion,
                trimester=insumo.trimestre,
                partial=insumo.parcial,
            )
        else:
            _save_insumo(
                insumo,
                name=target_name,
                kind=target_kind,
                weight=target_weight,
                trimester=insumo.trimestre,
                partial=insumo.parcial,
            )
            handled.add(key)


def ensure_required_insumos(curso, materia, docente, trimester, partial):
    normalize_misplaced_final_insumos(curso, materia)
    required = []
    if partial == 1:
        required.append(_ensure_insumo(
            curso,
            materia,
            docente,
            name=ONLINE_EVALUATION_NAME,
            kind=InsumoCalificacion.TIPO_EVALUACION,
            weight=ONLINE_EVALUATION_WEIGHT,
            trimester=trimester,
            partial=partial,
            reuse_types=(InsumoCalificacion.TIPO_EVALUACION, InsumoCalificacion.TIPO_EXAMEN_FINAL),
        ))
    else:
        required.append(_ensure_insumo(
            curso,
            materia,
            docente,
            name=METACOGNITION_NAME,
            kind=InsumoCalificacion.TIPO_EVALUACION,
            weight=METACOGNITION_WEIGHT,
            trimester=trimester,
            partial=partial,
            reuse_types=(InsumoCalificacion.TIPO_EVALUACION,),
        ))
        required.append(_ensure_insumo(
            curso,
            materia,
            docente,
            name=PHYSICAL_ASSESSMENT_NAME,
            kind=InsumoCalificacion.TIPO_INSUMO_2,
            weight=PHYSICAL_ASSESSMENT_WEIGHT,
            trimester=trimester,
            partial=partial,
            # Do not commandeer arbitrary Insumo 2 rows: they may be projects
            # or group activities that teachers need to keep as optional inputs.
        ))
    if trimester == 3 and partial == 2:
        required.append(_ensure_insumo(
            curso,
            materia,
            docente,
            name=FINAL_EXAM_NAME,
            kind=InsumoCalificacion.TIPO_EXAMEN_FINAL,
            weight=PESO_EXAMEN_FINAL,
            trimester=trimester,
            partial=partial,
            reuse_types=(InsumoCalificacion.TIPO_EXAMEN_FINAL,),
        ))
    return required


def is_required_insumo(insumo):
    if insumo.tipo == InsumoCalificacion.TIPO_EXAMEN_FINAL:
        return insumo.trimestre == 3 and insumo.parcial == 2
    if insumo.parcial == 1:
        return (
            insumo.tipo == InsumoCalificacion.TIPO_EVALUACION
            and insumo.nombre == ONLINE_EVALUATION_NAME
        )
    if insumo.parcial == 2:
        return (
            (insumo.tipo == InsumoCalificacion.TIPO_EVALUACION and insumo.nombre == METACOGNITION_NAME)
            or (insumo.tipo == InsumoCalificacion.TIPO_INSUMO_2 and insumo.nombre == PHYSICAL_ASSESSMENT_NAME)
        )
    return False


def sync_online_exam_attempt(attempt):
    exam = attempt.exam
    if (
        attempt.status != "submitted"
        or attempt.percentage is None
        or exam.trimestre not in (1, 2, 3)
        or exam.parcial != 1
        or not exam.materia_id
    ):
        return

    courses = list(exam.cursos.all())
    if exam.curso_id and all(course.pk != exam.curso_id for course in courses):
        courses.append(exam.curso)
    if not courses:
        courses = list(
            Curso.objects.filter(
                asignaciones__docente=exam.teacher,
                asignaciones__materia=exam.materia,
                asignaciones__activo=True,
                estudiantes=attempt.student,
            ).distinct()
        )
    for curso in courses:
        if not curso.estudiantes.filter(pk=attempt.student_id).exists():
            continue
        required = ensure_required_insumos(
            curso, exam.materia, exam.teacher, exam.trimestre, exam.parcial
        )
        online_insumo = next((item for item in required if item.nombre == ONLINE_EVALUATION_NAME), None)
        if online_insumo:
            _write_online_exam_grade(attempt, online_insumo)


def _write_online_exam_grade(attempt, insumo):
    nota = (attempt.percentage / Decimal("10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    RegistroCalificacion.objects.update_or_create(
        insumo=insumo,
        estudiante_id=attempt.student_id,
        defaults={"nota": nota},
    )


def sync_completed_online_exam_grades(curso, materia, trimester, partial):
    if partial != 1:
        return
    from django.db.models import Q
    from apps.intentos.models import Attempt

    online_insumo = InsumoCalificacion.objects.filter(
        curso=curso,
        materia=materia,
        trimestre=trimester,
        parcial=1,
        nombre=ONLINE_EVALUATION_NAME,
        tipo=InsumoCalificacion.TIPO_EVALUACION,
    ).first()
    if online_insumo is None:
        return

    course_students = curso.estudiantes.filter(is_active=True)
    attempts = Attempt.objects.filter(
        exam__materia=materia,
        exam__trimestre=trimester,
        exam__parcial=1,
        status=Attempt.Status.SUBMITTED,
        student__in=course_students,
    ).filter(
        Q(exam__curso=curso)
        | Q(exam__cursos=curso)
        | Q(
            exam__students__in=course_students,
            exam__teacher__asignaciones_docentes__curso=curso,
            exam__teacher__asignaciones_docentes__materia=materia,
            exam__teacher__asignaciones_docentes__activo=True,
        )
    ).select_related(
        "exam", "exam__teacher"
    ).distinct()
    for attempt in attempts:
        _write_online_exam_grade(attempt, online_insumo)
