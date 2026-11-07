import logging
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.evaluaciones.models import Exam, Option, Question
from apps.intentos.models import Answer, Attempt, Incident
from apps.intentos.services import finish_attempt
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

        attempt, created = Attempt.objects.get_or_create(
            exam=exam,
            student=request.user,
            defaults={"started_at": now},
        )
        if attempt.status == Attempt.Status.SUBMITTED:
            raise ValidationError("Ya existe un intento entregado para esta evaluación.")
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
        questions = attempt.exam.questions.prefetch_related("options").all()
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
                            for option in question.options.all()
                        ],
                        "selected_option_id": saved.get(question.pk),
                    }
                    for question in questions
                ],
            }
        )


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
                ticket_code = (
                    f"SEC-PROCTOR-{attempt.pk}-{previous_incident.pk}"
                    if previous_incident.kind in {
                        Incident.Kind.CAMERA_LOST,
                        Incident.Kind.MICROPHONE_LOST,
                        Incident.Kind.CAMERA_MUTED,
                        Incident.Kind.MICROPHONE_MUTED,
                    }
                    else None
                )
                focus_count = None
                if previous_incident.kind in {
                    Incident.Kind.TAB_HIDDEN,
                    Incident.Kind.WINDOW_BLUR,
                }:
                    focus_count = Incident.objects.filter(
                        attempt=attempt,
                        kind__in=[Incident.Kind.TAB_HIDDEN, Incident.Kind.WINDOW_BLUR],
                    ).count()
                return Response(
                    {
                        "received": True,
                        "duplicate": True,
                        "focus_offense_count": focus_count,
                        "auto_submitted": False,
                        "security_ticket_code": ticket_code,
                    },
                    status=status.HTTP_200_OK,
                )
        require_active(attempt)
        severity = (
            Incident.Severity.HIGH
            if kind in {Incident.Kind.CAMERA_LOST, Incident.Kind.MICROPHONE_LOST}
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
        security_ticket_code = None
        if kind in {
            Incident.Kind.CAMERA_LOST,
            Incident.Kind.MICROPHONE_LOST,
            Incident.Kind.CAMERA_MUTED,
            Incident.Kind.MICROPHONE_MUTED,
        }:
            security_ticket_code = f"SEC-PROCTOR-{attempt.pk}-{incident.pk}"
            if created:
                TicketAtencion.objects.create(
                    codigo=security_ticket_code,
                    tipo=TicketAtencion.Tipo.PROCTOR,
                    estudiante=attempt.student,
                    intento=attempt,
                    creado_por=request.user,
                )
        focus_offense_count = None
        auto_submitted = False
        if kind in {Incident.Kind.TAB_HIDDEN, Incident.Kind.WINDOW_BLUR}:
            focus_offense_count = Incident.objects.filter(
                attempt=attempt,
                kind__in=[Incident.Kind.TAB_HIDDEN, Incident.Kind.WINDOW_BLUR],
            ).count()
            if focus_offense_count >= 3 and attempt.status == Attempt.Status.IN_PROGRESS:
                finished, changed = finish_attempt(attempt.pk)
                auto_submitted = changed
                if changed:
                    create_report_safely(finished)
        elif kind in {
            Incident.Kind.CAMERA_LOST,
            Incident.Kind.MICROPHONE_LOST,
            Incident.Kind.CAMERA_MUTED,
            Incident.Kind.MICROPHONE_MUTED,
        }:
            finished, auto_submitted = finish_attempt(attempt.pk)
            if auto_submitted:
                create_report_safely(finished)
        return Response(
            {
                "received": True,
                "duplicate": not created,
                "focus_offense_count": focus_offense_count,
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
