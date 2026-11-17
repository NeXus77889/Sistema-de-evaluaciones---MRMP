import logging
import randomfrom apps.core.models import TicketAtencion

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
        raise ValidationError("El tiempo terminÃ³ y el intento fue entregado automÃ¡ticamente.")


def create_report_safely(attempt):
    try:
        from apps.reportes.services import create_and_email_report

        create_and_email_report(attempt.pk)
    except Exception:
        logger.exception("No se pudo generar o enviar el informe del intento %s", attempt.pk)


def ordered_questions(attempt):
    """Preguntas del intento, con opciones en `ordered_options`.

    Si la evaluaciÃ³n tiene orden aleatorio, la mezcla es distinta para cada intento pero
    estable: se genera con una semilla fija, asÃ­ que al recargar el estudiante ve lo mismo.
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

        if timezone.now() >= attempt.deadline:
            finished, changed = finish_attempt(attempt.pk)
            if changed:
                create_report_safely(finished)
            raise ValidationError("El tiempo de este intento ya terminÃ³.")
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
        questions = ordered_questions(attempt)        saved = dict(
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
                            for option in question.ordered_options                        ],
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
            "incident_count": strike_incidents(attempt).count(),            "incident_limit": 3,
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
                focus_count = strike_incidents(attempt).count()                return Response(
                    {
                        "received": True,
                        "duplicate": True,
                        "counts_as_strike": counts_as_strike,            else Incident.Severity.MEDIUM
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
        focus_offense_count = strike_incidents(attempt).count()        if focus_offense_count >= 3 and attempt.status == Attempt.Status.IN_PROGRESS:
            finished, auto_submitted = finish_attempt(attempt.pk)
            if auto_submitted:
                create_report_safely(finished)
        return Response(
            {
                "received": True,
                "duplicate": not created,
                "counts_as_strike": counts_as_strike,
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
