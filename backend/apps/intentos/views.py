import logging
<<<<<<< HEAD
import random
=======
>>>>>>> master
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.evaluaciones.models import Exam, Option, Question
<<<<<<< HEAD
from apps.intentos.models import NON_STRIKE_KINDS, Answer, Attempt, Incident, strike_incidents
from apps.intentos.services import finish_attempt
from apps.monitoreo.network import get_client_ip
=======
from apps.intentos.models import Answer, Attempt, Incident
from apps.intentos.services import finish_attempt
>>>>>>> master
from apps.core.models import TicketAtencion

logger = logging.getLogger(__name__)


class AnswerInput(serializers.Serializer):
    question_id = serializers.IntegerField(min_value=1)
    option_id = serializers.IntegerField(min_value=1, allow_null=True)


class IncidentInput(serializers.Serializer):
    kind = serializers.ChoiceField(choices=Incident.Kind.choices)
    duration_ms = serializers.IntegerField(min_value=0, max_value=86_400_000, required=False, allow_null=True)
    client_event_id = serializers.UUIDField(required=False)


def require_student(user):
    if user.rol != user.Role.STUDENT:
        raise PermissionDenied("Solo los estudiantes pueden realizar evaluaciones.")


def require_active(attempt):
    if attempt.status != Attempt.Status.IN_PROGRESS:
        raise ValidationError("El intento ya fue entregado.")
    if timezone.now() >= attempt.deadline:
        finished, changed = finish_attempt(attempt.pk)
        if changed:
            create_report_safely(finished)
        raise ValidationError("El tiempo terminó y el intento fue entregado automáticamente.")


def create_report_safely(attempt):
    try:
        from apps.reportes.services import create_and_email_report

        create_and_email_report(attempt.pk)
    except Exception:
        logger.exception("No se pudo generar o enviar el informe del intento %s", attempt.pk)


<<<<<<< HEAD
def ordered_questions(attempt):
    """Preguntas del intento, con opciones en `ordered_options`.

    Si la evaluación tiene orden aleatorio, la mezcla es distinta para cada intento pero
    estable: se genera con una semilla fija, así que al recargar el estudiante ve lo mismo.
    """
    questions = list(attempt.exam.questions.prefetch_related("options").all())
    for question in questions:
        question.ordered_options = list(question.options.all())
    if attempt.exam.randomize_order:
        rng = random.Random(f"intento-{attempt.pk}-{attempt.exam_id}")
        rng.shuffle(questions)
        for question in questions:
            rng.shuffle(question.ordered_options)
    return questions


=======
>>>>>>> master
class StartAttemptView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, exam_id):
        require_student(request.user)
        now = timezone.now()
        exam = get_object_or_404(Exam, pk=exam_id, published=True)
        if not exam.is_assigned_to_student(request.user):
            raise PermissionDenied("Esta evaluación no está asignada a tu usuario.")
        if now < exam.available_from or (exam.available_until and now >= exam.available_until):
            raise ValidationError("La evaluación no está disponible en este momento.")
        if not exam.questions.exists():
            raise ValidationError("La evaluación todavía no tiene preguntas.")
        for question in exam.questions.prefetch_related("options"):
            options = list(question.options.all())
            if len(options) < 2 or sum(option.is_correct for option in options) != 1:
                raise ValidationError("La evaluación contiene una pregunta incompleta.")

<<<<<<< HEAD
        # La IP solo se registra si el docente activó la detección en esta evaluación.
        client_ip = get_client_ip(request) if exam.detect_nearby_ips else None
        attempt, created = Attempt.objects.get_or_create(
            exam=exam,
            student=request.user,
            defaults={"started_at": now, "ip_address": client_ip},
        )
        if attempt.status == Attempt.Status.SUBMITTED:
            raise ValidationError("Ya existe un intento entregado para esta evaluación.")
        if client_ip and not attempt.ip_address:
            attempt.ip_address = client_ip
            attempt.save(update_fields=["ip_address"])
=======
        attempt, created = Attempt.objects.get_or_create(
            exam=exam,
            student=request.user,
            defaults={"started_at": now},
        )
        if attempt.status == Attempt.Status.SUBMITTED:
            raise ValidationError("Ya existe un intento entregado para esta evaluación.")
>>>>>>> master
        if timezone.now() >= attempt.deadline:
            finished, changed = finish_attempt(attempt.pk)
            if changed:
                create_report_safely(finished)
            raise ValidationError("El tiempo de este intento ya terminó.")
        if created:
            attempt.refresh_from_db()
        return Response(
            {
                "attempt_id": attempt.pk,
                "deadline": attempt.deadline,
                "duration_seconds": exam.duration_minutes * 60,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class AttemptStateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, attempt_id):
        require_student(request.user)
        attempt = get_object_or_404(
            Attempt.objects.select_related("exam"), pk=attempt_id, student=request.user
        )
        if attempt.status == Attempt.Status.IN_PROGRESS and timezone.now() >= attempt.deadline:
            attempt, changed = finish_attempt(attempt.pk)
            if changed:
                create_report_safely(attempt)
<<<<<<< HEAD
        questions = ordered_questions(attempt)
=======
        questions = attempt.exam.questions.prefetch_related("options").all()
>>>>>>> master
        saved = dict(
            Answer.objects.filter(attempt=attempt).values_list("question_id", "selected_option_id")
        )
        return Response(
            {
                "attempt_id": attempt.pk,
                "exam_title": attempt.exam.title,
                "status": attempt.status,
                "deadline": attempt.deadline,
                "questions": [
                    {
                        "id": question.pk,
                        "text": question.text,
                        "position": question.position,
                        "options": [
                            {"id": option.pk, "text": option.text, "position": option.position}
<<<<<<< HEAD
                            for option in question.ordered_options
=======
                            for option in question.options.all()
>>>>>>> master
                        ],
                        "selected_option_id": saved.get(question.pk),
                    }
                    for question in questions
                ],
            }
        )


class AttemptIncidentCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, attempt_id):
        require_student(request.user)
        attempt = get_object_or_404(Attempt, pk=attempt_id, student=request.user)
        return Response({
            "attempt_id": attempt.pk,
<<<<<<< HEAD
            "incident_count": strike_incidents(attempt).count(),
=======
            "incident_count": Incident.objects.filter(attempt=attempt).count(),
>>>>>>> master
            "incident_limit": 3,
            "status": attempt.status,
        })


class SaveAnswerView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, attempt_id):
        require_student(request.user)
        attempt = get_object_or_404(
            Attempt.objects.select_for_update(), pk=attempt_id, student=request.user
        )
        require_active(attempt)
        serializer = AnswerInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        question = get_object_or_404(Question, pk=values["question_id"], exam=attempt.exam)
        option = None
        if values["option_id"] is not None:
            option = get_object_or_404(Option, pk=values["option_id"], question=question)
        Answer.objects.update_or_create(
            attempt=attempt,
            question=question,
            defaults={"selected_option": option},
        )
        return Response({"saved": True})


class RecordIncidentView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, attempt_id):
        require_student(request.user)
        attempt = get_object_or_404(
            Attempt.objects.select_for_update(), pk=attempt_id, student=request.user
        )
        serializer = IncidentInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        kind = values["kind"]
        event_id = values.get("client_event_id")
        if event_id:
            previous_incident = Incident.objects.filter(
                client_event_id=event_id
            ).first()
            if previous_incident:
                if previous_incident.attempt_id != attempt.pk:
                    raise ValidationError("El identificador del evento ya fue utilizado.")
<<<<<<< HEAD
                counts_as_strike = previous_incident.kind not in NON_STRIKE_KINDS
                ticket_code = None
                if counts_as_strike:
                    ticket_code = f"SEC-PROCTOR-{attempt.pk}-{previous_incident.pk}"
                    TicketAtencion.objects.get_or_create(
                        codigo=ticket_code,
                        defaults={
                            "tipo": TicketAtencion.Tipo.PROCTOR,
                            "estudiante": attempt.student,
                            "intento": attempt,
                            "creado_por": request.user,
                        },
                    )
                focus_count = strike_incidents(attempt).count()
=======
                ticket_code = f"SEC-PROCTOR-{attempt.pk}-{previous_incident.pk}"
                TicketAtencion.objects.get_or_create(
                    codigo=ticket_code,
                    defaults={
                        "tipo": TicketAtencion.Tipo.PROCTOR,
                        "estudiante": attempt.student,
                        "intento": attempt,
                        "creado_por": request.user,
                    },
                )
                focus_count = Incident.objects.filter(attempt=attempt).count()
>>>>>>> master
                return Response(
                    {
                        "received": True,
                        "duplicate": True,
<<<<<<< HEAD
                        "counts_as_strike": counts_as_strike,
=======
>>>>>>> master
                        "focus_offense_count": focus_count,
                        "incident_count": focus_count,
                        "auto_submitted": False,
                        "security_ticket_code": ticket_code,
                    },
                    status=status.HTTP_200_OK,
                )
        require_active(attempt)
        severity = (
            Incident.Severity.HIGH
<<<<<<< HEAD
            if kind in {Incident.Kind.CAMERA_LOST, Incident.Kind.MICROPHONE_LOST, Incident.Kind.PHONE_DETECTED}
=======
            if kind in {Incident.Kind.CAMERA_LOST, Incident.Kind.MICROPHONE_LOST}
>>>>>>> master
            else Incident.Severity.MEDIUM
        )
        incident_values = {
            "attempt": attempt,
            "kind": kind,
            "duration_ms": values.get("duration_ms"),
            "description": Incident.Kind(kind).label,
            "severity": severity,
        }
        if event_id:
            incident, created = Incident.objects.get_or_create(
                client_event_id=event_id,
                defaults=incident_values,
            )
        else:
            incident = Incident.objects.create(**incident_values)
            created = True
        if incident.attempt_id != attempt.pk:
            raise ValidationError("El identificador del evento ya fue utilizado.")
<<<<<<< HEAD
        counts_as_strike = kind not in NON_STRIKE_KINDS
        security_ticket_code = None
        if counts_as_strike:
            security_ticket_code = f"SEC-PROCTOR-{attempt.pk}-{incident.pk}"
            TicketAtencion.objects.get_or_create(
                codigo=security_ticket_code,
                defaults={
                    "tipo": TicketAtencion.Tipo.PROCTOR,
                    "estudiante": attempt.student,
                    "intento": attempt,
                    "creado_por": request.user,
                },
            )
        auto_submitted = False
        focus_offense_count = strike_incidents(attempt).count()
=======
        security_ticket_code = f"SEC-PROCTOR-{attempt.pk}-{incident.pk}"
        TicketAtencion.objects.get_or_create(
            codigo=security_ticket_code,
            defaults={
                "tipo": TicketAtencion.Tipo.PROCTOR,
                "estudiante": attempt.student,
                "intento": attempt,
                "creado_por": request.user,
            },
        )
        focus_offense_count = None
        auto_submitted = False
        focus_offense_count = Incident.objects.filter(attempt=attempt).count()
>>>>>>> master
        if focus_offense_count >= 3 and attempt.status == Attempt.Status.IN_PROGRESS:
            finished, auto_submitted = finish_attempt(attempt.pk)
            if auto_submitted:
                create_report_safely(finished)
        return Response(
            {
                "received": True,
                "duplicate": not created,
<<<<<<< HEAD
                "counts_as_strike": counts_as_strike,
=======
>>>>>>> master
                "focus_offense_count": focus_offense_count,
                "incident_count": focus_offense_count,
                "auto_submitted": auto_submitted,
                "security_ticket_code": security_ticket_code,
            },
            status=status.HTTP_200_OK,
        )


class SubmitAttemptView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, attempt_id):
        require_student(request.user)
        attempt = get_object_or_404(Attempt, pk=attempt_id, student=request.user)
        finished, changed = finish_attempt(attempt.pk)
        if changed:
            create_report_safely(finished)
        return Response(
            {"submitted": True, "results_visible": finished.exam.results_visible,
             **({"score": str(finished.score), "percentage": str(finished.percentage)}
                if finished.exam.results_visible else {})}
        )
