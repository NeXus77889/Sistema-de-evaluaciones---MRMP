import json
import re
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.views import PasswordChangeView
from django.core.exceptions import ValidationError
from django.db.models import Prefetch, Q
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.evaluaciones.forms import ExamForm
from apps.evaluaciones.academic import (
    DASHBOARD_LEVEL_LABELS,
    course_level,
    course_sort_key,
    group_items_by_level,
)
from apps.evaluaciones.docx_import import DocxImportError, parse_docx_questions
from apps.evaluaciones.models import Exam, Option, Question
from apps.evaluaciones.models import Curso
from apps.intentos.models import Attempt, Incident
from apps.core.models import TicketAtencion
from apps.usuarios.models import User


class SignInView(LoginView):
    template_name = "auth/login.html"
    redirect_authenticated_user = True


class SignOutView(LogoutView):
    http_method_names = ["post", "options"]


class AccountPasswordChangeView(PasswordChangeView):
    template_name = "auth/password_change.html"
    success_url = reverse_lazy("dashboard")

    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.user.debe_cambiar_password = False
        self.request.user.save(update_fields=["debe_cambiar_password"])
        update_session_auth_hash(self.request, self.request.user)
        messages.success(self.request, "La contraseña se actualizó correctamente.")
        return response


def _is_secretary(user):
    return user.is_authenticated and user.is_staff and user.rol == User.Role.ADMINISTRATOR


def _teacher_incident_groups(teacher):
    incidents = list(
        Incident.objects.filter(
            attempt__exam__teacher=teacher,
        )
        .select_related("attempt__student", "attempt__exam__curso")
        .prefetch_related("attempt__student__cursos", "attempt__exam__cursos")
        .order_by("-occurred_at", "-pk")
    )
    ticket_codes = [
        f"SEC-PROCTOR-{incident.attempt_id}-{incident.pk}"
        for incident in incidents
        if incident.kind in {
            Incident.Kind.CAMERA_LOST,
            Incident.Kind.MICROPHONE_LOST,
            Incident.Kind.CAMERA_MUTED,
            Incident.Kind.MICROPHONE_MUTED,
        }
    ]
    ticket_states = dict(
        TicketAtencion.objects.filter(
            tipo=TicketAtencion.Tipo.PROCTOR,
            codigo__in=ticket_codes,
        ).values_list("codigo", "estado")
    )
    grouped = {}
    for incident in incidents:
        attempt = incident.attempt
        exam = attempt.exam
        courses = list(exam.cursos.all())
        if exam.curso_id and all(course.pk != exam.curso_id for course in courses):
            courses.append(exam.curso)
        enrolled_course_ids = {course.pk for course in attempt.student.cursos.all()}
        matched_courses = [course for course in courses if course.pk in enrolled_course_ids]
        if not matched_courses:
            matched_courses = courses[:1]
        if not matched_courses:
            matched_courses = [None]
        matched_courses = [
            min((course for course in matched_courses if course), key=course_sort_key)
            if any(matched_courses)
            else None
        ]

        ticket_code = f"SEC-PROCTOR-{attempt.pk}-{incident.pk}"
        incident.ticket_code = (
            ticket_code
            if incident.kind in {
                Incident.Kind.CAMERA_LOST,
                Incident.Kind.MICROPHONE_LOST,
                Incident.Kind.CAMERA_MUTED,
                Incident.Kind.MICROPHONE_MUTED,
            }
            else ""
        )
        ticket_state = ticket_states.get(ticket_code)
        incident.ticket_state = (
            TicketAtencion.Estado(ticket_state).label
            if ticket_state
            else "Registrada" if not incident.ticket_code else "Ticket no encontrado"
        )

        for course in matched_courses:
            course_key = course.pk if course else None
            incident.filter_course_id = str(course_key) if course_key else "none"
            incident.course_name = str(course) if course else "Sin curso asociado"
            incident.filter_date = incident.occurred_at.date().isoformat()
            course_group = grouped.setdefault(
                course_key,
                {
                    "course": course,
                    "course_name": str(course) if course else "Sin curso asociado",
                    "students": {},
                },
            )
            student_group = course_group["students"].setdefault(
                attempt.student_id,
                {
                    "student": attempt.student,
                    "student_name": attempt.student.get_full_name()
                    or attempt.student.username,
                    "incidents": [],
                },
            )
            student_group["incidents"].append(incident)

    course_groups = sorted(
        grouped.values(),
        key=lambda group: course_sort_key(group["course"])
        if group["course"]
        else (99, 99, "", ""),
    )
    for course_group in course_groups:
        course_group["students"] = sorted(
            course_group["students"].values(),
            key=lambda student: student["student_name"].casefold(),
        )
        course_group["student_count"] = len(course_group["students"])
    return course_groups


def _course_for_exam_student(exam, student):
    courses = list(exam.cursos.all())
    if exam.curso_id and all(course.pk != exam.curso_id for course in courses):
        courses.append(exam.curso)
    if student and courses:
        enrolled_ids = {course.pk for course in student.cursos.all()}
        enrolled_courses = [course for course in courses if course.pk in enrolled_ids]
        if enrolled_courses:
            courses = enrolled_courses
    return min(courses, key=course_sort_key) if courses else None


def _ticket_groups_by_level(tickets):
    grouped = {key: {} for key in DASHBOARD_LEVEL_LABELS}
    for ticket in tickets:
        student = ticket.estudiante or (
            ticket.intento.student if ticket.intento_id else None
        )
        course = (
            _course_for_exam_student(ticket.intento.exam, student)
            if ticket.intento_id
            else None
        )
        if course is None and student:
            student_courses = list(student.cursos.all())
            course = min(student_courses, key=course_sort_key) if student_courses else None
        level = course_level(course) if course else "other"
        ticket.student_name = (
            (student.get_full_name() or student.username) if student else "Sin identificar"
        )
        ticket.student_identification = student.identification if student else ""
        ticket.type_code = f"SEC-{ticket.tipo}"
        ticket.filter_course_id = str(course.pk) if course else "none"
        ticket.course_name = str(course) if course else "Sin curso asociado"
        ticket.filter_date = ticket.creado_en.date().isoformat()
        course_key = course.pk if course else None
        course_group = grouped[level].setdefault(
            course_key,
            {"course": course, "course_name": ticket.course_name, "students": {}},
        )
        student_key = student.pk if student else None
        student_group = course_group["students"].setdefault(
            student_key,
            {
                "student_name": ticket.student_name,
                "student_identification": ticket.student_identification,
                "tickets": [],
            },
        )
        student_group["tickets"].append(ticket)

    result = []
    for key, label in DASHBOARD_LEVEL_LABELS.items():
        course_groups = []
        tickets_in_level = []
        for course_group in grouped[key].values():
            students = []
            for student_group in course_group["students"].values():
                student_group["tickets"].sort(
                    key=lambda ticket: (ticket.creado_en, ticket.pk), reverse=True
                )
                students.append(student_group)
                tickets_in_level.extend(student_group["tickets"])
            course_group["students"] = sorted(
                students, key=lambda group: group["student_name"].casefold()
            )
            course_groups.append(course_group)
        course_groups.sort(
            key=lambda group: course_sort_key(group["course"])
            if group["course"]
            else (99, 99, "", "")
        )
        if course_groups:
            result.append(
                {
                    "key": key,
                    "label": label,
                    "course_groups": course_groups,
                    "items": tickets_in_level,
                }
            )
    return result


def _prepare_incidents(incidents):
    for incident in incidents:
        course = _course_for_exam_student(incident.attempt.exam, incident.attempt.student)
        incident.filter_course_id = str(course.pk) if course else "none"
        incident.course_name = str(course) if course else "Sin curso asociado"
        incident.filter_date = incident.occurred_at.date().isoformat()
    return incidents


def _group_by_subject(items, exam_getter=lambda item: item):
    grouped = {}
    for item in items:
        subject = exam_getter(item).materia
        label = subject.nombre if subject else "Sin materia"
        grouped.setdefault(label, []).append(item)
    return [
        {"label": label, "items": grouped[label]}
        for label in sorted(grouped, key=str.casefold)
    ]


@require_POST
def create_support_ticket(request):
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Solicitud inválida."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "Solicitud inválida."}, status=400)

    kind = payload.get("tipo")
    code = str(payload.get("codigo", "")).strip().upper()
    identification = re.sub(r"\D", "", str(payload.get("identificacion", "")))
    contact_email = str(payload.get("correo", "")).strip().lower()
    patterns = {
        "PASS": r"^SEC-PASS-\d{6,40}$",
        "USER": r"^SEC-USER-\d{6}$",
        "EXAM": r"^SEC-EXAM-\d+-\d{6,40}$",
    }
    if not isinstance(kind, str) or kind not in patterns or not re.fullmatch(patterns[kind], code):
        return JsonResponse({"error": "Tipo o código de atención inválido."}, status=400)
    if contact_email:
        from django.core.validators import validate_email

        try:
            validate_email(contact_email)
        except ValidationError:
            return JsonResponse({"error": "El correo no es válido."}, status=400)

    student = None
    attempt = None
    if kind == "PASS":
        if identification and code != f"SEC-PASS-{identification}":
            return JsonResponse({"error": "La cédula no coincide con el código."}, status=400)
        if not identification and not contact_email:
            return JsonResponse(
                {"error": "Indica una cédula o correo para localizar la cuenta."},
                status=400,
            )
        if identification:
            student = User.objects.filter(
                Q(identification=identification) | Q(username=identification),
                rol=User.Role.STUDENT,
            ).first()
        elif contact_email:
            student = User.objects.filter(
                email__iexact=contact_email,
                rol=User.Role.STUDENT,
            ).first()
    elif kind == "USER":
        if not contact_email:
            return JsonResponse({"error": "Indica el correo registrado."}, status=400)
        student = User.objects.filter(
            email__iexact=contact_email,
            rol=User.Role.STUDENT,
        ).first()
    else:
        if not request.user.is_authenticated or request.user.rol != User.Role.STUDENT:
            return JsonResponse({"error": "Debes iniciar sesión como estudiante."}, status=403)
        match = re.fullmatch(r"SEC-EXAM-(\d+)-(\d{6,40})", code)
        exam_id, code_identification = match.groups()
        attempt_id = str(payload.get("intento_id", ""))
        if not attempt_id.isdecimal():
            return JsonResponse({"error": "El intento indicado no es válido."}, status=400)
        student_identification = re.sub(r"\D", "", request.user.identification)
        if code_identification != student_identification:
            return JsonResponse({"error": "La cédula del código no coincide."}, status=400)
        attempt = Attempt.objects.filter(
            pk=attempt_id,
            exam_id=exam_id,
            student=request.user,
        ).first()
        if attempt is None:
            return JsonResponse({"error": "El intento no existe para esta cuenta."}, status=404)
        student = request.user

    ticket = TicketAtencion.objects.filter(
        codigo=code,
        tipo=kind,
        estado=TicketAtencion.Estado.PENDIENTE,
        estudiante=student,
        intento=attempt,
        correo_contacto=contact_email,
    ).order_by("-creado_en", "-pk").first()
    created = ticket is None
    if created:
        ticket = TicketAtencion.objects.create(
            codigo=code,
            tipo=kind,
            correo_contacto=contact_email,
            estudiante=student,
            intento=attempt,
            creado_por=request.user if request.user.is_authenticated else None,
        )
    return JsonResponse(
        {"ticket_id": ticket.pk, "codigo": ticket.codigo},
        status=201 if created else 200,
    )


@require_POST
@login_required
def ticket_attention(request):
    if not _is_secretary(request.user):
        return HttpResponseForbidden()

    code = str(request.POST.get("codigo", "")).strip().upper()
    ticket = TicketAtencion.objects.filter(
        codigo=code,
        estado=TicketAtencion.Estado.PENDIENTE,
    ).order_by("-creado_en", "-pk").first()
    if ticket is None:
        already_resolved = TicketAtencion.objects.filter(
            codigo=code,
            estado=TicketAtencion.Estado.RESUELTO,
        ).exists()
        if already_resolved:
            messages.warning(request, "Ese ticket ya fue resuelto.")
            return redirect("dashboard")
        messages.error(request, "No se encontró un ticket pendiente con ese código.")
        return redirect("dashboard")

    if ticket.tipo == TicketAtencion.Tipo.PASSWORD:
        student = ticket.estudiante
        if student is None and ticket.correo_contacto:
            student = User.objects.filter(
                email__iexact=ticket.correo_contacto,
                rol=User.Role.STUDENT,
            ).first()
        if student is None:
            identification = code.removeprefix("SEC-PASS-")
            student = User.objects.filter(
                Q(identification=identification) | Q(username=identification),
                rol=User.Role.STUDENT,
            ).first()
        if student is None:
            messages.error(request, "No se encontró la cuenta. Verifica la cédula o correo.")
            return redirect("dashboard")
        ticket.estudiante = student
        ticket.save(update_fields=["estudiante"])
        return redirect("ticket-password", ticket_id=ticket.pk)

    if ticket.tipo == TicketAtencion.Tipo.USER:
        return redirect("ticket-user-info", ticket_id=ticket.pk)

    if ticket.tipo == TicketAtencion.Tipo.PROCTOR:
        if ticket.intento_id is None:
            messages.error(request, "El ticket de proctoring no tiene un intento asociado.")
            return redirect("dashboard")
        return redirect(reverse("admin:intentos_attempt_change", args=[ticket.intento_id]))

    attempt = ticket.intento
    if attempt is None:
        match = re.fullmatch(r"SEC-EXAM-(\d+)-(\d{6,40})", code)
        if match:
            exam_id, identification = match.groups()
            attempt = Attempt.objects.filter(
                exam_id=exam_id,
                student__identification=identification,
            ).first()
    if attempt is None:
        messages.error(request, "No se encontró un intento asociado a ese ticket.")
        return redirect("dashboard")
    ticket.intento = attempt
    ticket.estudiante = attempt.student
    ticket.save(update_fields=["intento", "estudiante"])
    return redirect(reverse("admin:intentos_attempt_change", args=[attempt.pk]))


@login_required
@require_http_methods(["GET", "POST"])
def ticket_password(request, ticket_id):
    if not _is_secretary(request.user):
        return HttpResponseForbidden()
    ticket = get_object_or_404(
        TicketAtencion.objects.select_related("estudiante"),
        pk=ticket_id,
        tipo=TicketAtencion.Tipo.PASSWORD,
        estado=TicketAtencion.Estado.PENDIENTE,
    )
    if ticket.estudiante is None:
        raise Http404
    form = SetPasswordForm(ticket.estudiante, request.POST or None)
    if request.method == "POST" and form.is_valid():
        student = form.save()
        student.debe_cambiar_password = True
        student.save(update_fields=["debe_cambiar_password"])
        ticket.estado = TicketAtencion.Estado.RESUELTO
        ticket.atendido_por = request.user
        ticket.atendido_en = timezone.now()
        ticket.save(update_fields=["estado", "atendido_por", "atendido_en"])
        messages.success(request, "Clave temporal actualizada y ticket resuelto.")
        return redirect("dashboard")
    return render(
        request,
        "admin/secretaria/ticket_password.html",
        {"ticket": ticket, "form": form},
    )


@login_required
@require_http_methods(["GET", "POST"])
def ticket_user_info(request, ticket_id):
    if not _is_secretary(request.user):
        return HttpResponseForbidden()
    ticket = get_object_or_404(
        TicketAtencion.objects.select_related("estudiante"),
        pk=ticket_id,
        tipo=TicketAtencion.Tipo.USER,
    )
    if request.method == "POST" and ticket.estado == TicketAtencion.Estado.PENDIENTE:
        ticket.estado = TicketAtencion.Estado.RESUELTO
        ticket.atendido_por = request.user
        ticket.atendido_en = timezone.now()
        ticket.save(update_fields=["estado", "atendido_por", "atendido_en"])
        messages.success(request, "Ticket marcado como resuelto.")
        return redirect("dashboard")
    courses = ticket.estudiante.cursos.all() if ticket.estudiante else []
    return render(
        request,
        "admin/secretaria/ticket_user_info.html",
        {"ticket": ticket, "courses": courses},
    )


@login_required
def dashboard(request):
    user = request.user
    if user.rol == User.Role.ADMINISTRATOR:
        exams = list(
            Exam.objects.select_related("teacher", "materia", "curso")
            .prefetch_related("cursos")[:12]
        )
        context = {
            "user_count": User.objects.count(),
            "teacher_count": User.objects.filter(rol=User.Role.TEACHER, is_active=True).count(),
            "student_count": User.objects.filter(rol=User.Role.STUDENT, is_active=True).count(),
            "exam_count": Exam.objects.count(),
            "attempt_count": Attempt.objects.count(),
            "incident_count": Incident.objects.count(),
            "recent_incidents": _prepare_incidents(
                Incident.objects.select_related(
                    "attempt__student", "attempt__exam__curso"
                ).prefetch_related(
                    "attempt__student__cursos", "attempt__exam__cursos"
                ).order_by("-occurred_at")
            ),
            "filter_courses": sorted(Curso.objects.all(), key=course_sort_key),
            "ticket_groups": _ticket_groups_by_level(
                TicketAtencion.objects.select_related(
                    "estudiante", "atendido_por", "intento__student", "intento__exam__curso"
                ).prefetch_related(
                    "estudiante__cursos", "intento__student__cursos", "intento__exam__cursos"
                )
            ),
            "exam_groups": group_items_by_level(exams),
        }
        return render(request, "admin/dashboard.html", context)
    if user.rol == User.Role.TEACHER:
        exams = list(
            Exam.objects.filter(teacher=user)
            .select_related("curso", "materia")
            .prefetch_related("students", "cursos")[:12]
        )
        attempts = Attempt.objects.filter(exam__teacher=user).select_related("exam", "student")
        context = {
            "exams": exams,
            "exam_groups": group_items_by_level(exams),
            "attempt_count": attempts.count(),
            "completed_count": attempts.filter(status=Attempt.Status.SUBMITTED).count(),
            "incident_count": Incident.objects.filter(attempt__exam__teacher=user).count(),
            "recent_attempts": attempts.order_by("-started_at")[:8],
            "recent_incidents": Incident.objects.filter(attempt__exam__teacher=user)
            .select_related("attempt__student", "attempt__exam")[:8],
            "incidence_groups": _teacher_incident_groups(user),
            "filter_courses": sorted(Curso.objects.all(), key=course_sort_key),
        }
        return render(request, "docente/dashboard.html", context)
    now = timezone.now()
    exams = Exam.objects.filter(
        Q(students=user) | Q(curso__estudiantes=user) | Q(cursos__estudiantes=user),
        published=True,
        available_from__lte=now,
    ).filter(Q(available_until__isnull=True) | Q(available_until__gt=now)).prefetch_related(
        Prefetch("attempts", queryset=Attempt.objects.filter(student=user), to_attr="my_attempts")
    )
    exams = list(
        exams.distinct()
        .select_related("teacher", "materia", "curso")
        .prefetch_related("cursos")
    )
    attempts = list(
        Attempt.objects.filter(student=user)
        .select_related("exam", "exam__curso", "exam__teacher", "exam__materia")
        .prefetch_related("exam__cursos")
    )
    return render(
        request,
        "estudiante/dashboard.html",
        {
            "exams": exams,
            "exam_groups": group_items_by_level(exams),
            "subject_groups": _group_by_subject(exams),
            "attempts": attempts,
            "attempt_groups": group_items_by_level(attempts, lambda attempt: attempt.exam),
            "attempt_subject_groups": _group_by_subject(
                attempts, lambda attempt: attempt.exam
            ),
        },
    )


@login_required
def exam_edit(request, exam_id=None):
    if request.user.rol != User.Role.TEACHER:
        raise Http404
    exam = get_object_or_404(Exam, pk=exam_id, teacher=request.user) if exam_id else None
    if exam and exam.attempts.exists():
        messages.error(request, "Esta evaluación ya tiene intentos y no se puede modificar.")
        return redirect("dashboard")
    questions = list(exam.questions.prefetch_related("options")) if exam else []
    if request.method == "POST":
        form = ExamForm(request.POST, instance=exam, docente=request.user)
        try:
            question_data = json.loads(request.POST.get("questions_json", "[]"))
            validated_questions = validate_question_data(question_data)
        except (json.JSONDecodeError, ValueError, TypeError) as error:
            validated_questions = None
            form.add_error(None, str(error))
        if form.is_valid() and validated_questions is not None:
            with transaction.atomic():
                saved_exam = form.save(commit=False)
                saved_exam.teacher = request.user
                saved_exam.full_clean()
                saved_exam.save()
                form.save_m2m()
                saved_exam.questions.all().delete()
                for position, question_data in enumerate(validated_questions, start=1):
                    question = Question.objects.create(
                        exam=saved_exam,
                        text=question_data["text"],
                        points=question_data["points"],
                        position=position,
                    )
                    Option.objects.bulk_create([
                        Option(
                            question=question,
                            text=option["text"],
                            is_correct=option["correct"],
                            position=option_position,
                        )
                        for option_position, option in enumerate(question_data["options"], start=1)
                    ])
            messages.success(request, "La evaluación se guardó correctamente.")
            return redirect("dashboard")
    else:
        form = ExamForm(instance=exam, docente=request.user)
    question_data = [
        {
            "text": question.text,
            "points": str(question.points),
            "options": [{"text": option.text, "correct": option.is_correct} for option in question.options.all()],
        }
        for question in questions
    ]
    return render(request, "docente/exam_form.html", {"form": form, "exam": exam, "question_data": question_data})


@require_POST
@login_required
def exam_import_preview(request):
    if request.user.rol != User.Role.TEACHER:
        raise Http404
    uploaded_file = request.FILES.get("archivo")
    if uploaded_file is None:
        return JsonResponse({"detail": "Selecciona un documento .docx."}, status=400)
    if not uploaded_file.name.lower().endswith(".docx"):
        return JsonResponse({"detail": "El archivo debe tener formato .docx."}, status=400)
    if uploaded_file.size > 10 * 1024 * 1024:
        return JsonResponse({"detail": "El documento no puede superar 10 MB."}, status=400)
    try:
        questions = parse_docx_questions(uploaded_file)
    except DocxImportError as error:
        return JsonResponse({"detail": str(error)}, status=400)
    return JsonResponse({"questions": questions})


def validate_question_data(data):
    if not isinstance(data, list) or not data:
        raise ValueError("Agrega al menos una pregunta.")
    if len(data) > 100:
        raise ValueError("Una evaluación admite hasta 100 preguntas.")
    validated = []
    for question in data:
        if not isinstance(question, dict):
            raise ValueError("Formato de pregunta inválido.")
        text = str(question.get("text", "")).strip()
        if not text or len(text) > 5000:
            raise ValueError("Cada pregunta requiere texto de hasta 5000 caracteres.")
        try:
            points = Decimal(str(question.get("points", "1")))
        except InvalidOperation as error:
            raise ValueError("El puntaje debe ser numérico.") from error
        if not points.is_finite() or points <= 0 or points > 99999:
            raise ValueError("El puntaje debe ser mayor que cero y menor que 100000.")
        options = question.get("options")
        if not isinstance(options, list) or not 2 <= len(options) <= 12:
            raise ValueError("Cada pregunta requiere entre 2 y 12 opciones.")
        clean_options = []
        for option in options:
            if not isinstance(option, dict):
                raise ValueError("Formato de opción inválido.")
            option_text = str(option.get("text", "")).strip()
            if not option_text or len(option_text) > 1000:
                raise ValueError("Cada opción requiere texto de hasta 1000 caracteres.")
            clean_options.append({"text": option_text, "correct": option.get("correct") is True})
        if sum(option["correct"] for option in clean_options) != 1:
            raise ValueError("Cada pregunta debe tener exactamente una respuesta correcta.")
        validated.append({"text": text, "points": points, "options": clean_options})
    return validated


@require_POST
@login_required
def exam_delete(request, exam_id):
    if request.user.rol != User.Role.TEACHER:
        raise Http404
    exam = get_object_or_404(Exam, pk=exam_id, teacher=request.user)
    if exam.attempts.exists():
        messages.error(request, "No se puede eliminar una evaluación que ya tiene intentos.")
    else:
        exam.delete()
        messages.success(request, "La evaluación fue eliminada.")
    return redirect("dashboard")


@login_required
def exam_results(request, exam_id):
    if request.user.rol == User.Role.TEACHER:
        exam = get_object_or_404(Exam, pk=exam_id, teacher=request.user)
    elif request.user.rol == User.Role.ADMINISTRATOR:
        exam = get_object_or_404(Exam, pk=exam_id)
    else:
        raise Http404
    attempts = exam.attempts.select_related("student").prefetch_related("incidents")
    return render(request, "docente/results.html", {"exam": exam, "attempts": attempts})


@login_required
def exam_launch(request, exam_id):
    if request.user.rol != User.Role.STUDENT:
        raise Http404
    exam = get_object_or_404(
        Exam.objects.select_related("teacher", "materia", "curso").prefetch_related(
            "cursos",
            "students",
        ),
        pk=exam_id,
    )
    now = timezone.now()
    launch_error = None
    if not exam.published:
        launch_error = "Esta evaluación todavía no ha sido publicada."
    elif not exam.is_assigned_to_student(request.user):
        launch_error = "Esta evaluación no está asignada a tu curso ni a tu usuario."
    elif now < exam.available_from:
        launch_error = "La evaluación todavía no está disponible."
    elif exam.available_until and now >= exam.available_until:
        launch_error = "El período disponible para esta evaluación terminó."
    return render(
        request,
        "estudiante/launch.html",
        {"exam": exam, "launch_error": launch_error},
    )


@login_required
def exam_runner(request, attempt_id):
    if request.user.rol != User.Role.STUDENT:
        raise Http404
    attempt = get_object_or_404(Attempt.objects.select_related("exam"), pk=attempt_id, student=request.user)
    return render(request, "estudiante/exam.html", {"attempt": attempt})


@login_required
def result_detail(request, attempt_id):
    attempt = get_object_or_404(
        Attempt.objects.select_related("exam", "student", "exam__teacher"), pk=attempt_id
    )
    is_admin = request.user.rol == User.Role.ADMINISTRATOR
    is_teacher = request.user == attempt.exam.teacher
    is_visible_student = (
        request.user == attempt.student
        and attempt.exam.results_visible
        and attempt.status == Attempt.Status.SUBMITTED
    )
    if not (is_admin or is_teacher or is_visible_student):
        raise Http404
    incidents = attempt.incidents.all()
    return render(request, "estudiante/result.html", {"attempt": attempt, "incidents": incidents})


@login_required
def report_download(request, attempt_id):
    attempt = get_object_or_404(
        Attempt.objects.select_related("exam", "exam__teacher"), pk=attempt_id
    )
    can_access = (
        request.user.rol == User.Role.ADMINISTRATOR
        or request.user == attempt.exam.teacher
        or (
            request.user == attempt.student
            and attempt.exam.results_visible
            and attempt.status == Attempt.Status.SUBMITTED
        )
    )
    if not can_access or not hasattr(attempt, "report") or not attempt.report.pdf:
        raise Http404
    return FileResponse(
        attempt.report.pdf.open("rb"),
        as_attachment=True,
        filename=f"informe_intento_{attempt.pk}.pdf",
        content_type="application/pdf",
    )