from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.evaluaciones.models import Option
from apps.monitoreo.services import assess_attempt
from apps.intentos.models import Answer, Attempt


@transaction.atomic
def finish_attempt(attempt_id):
    attempt = Attempt.objects.select_for_update().select_related("exam").get(pk=attempt_id)
    if attempt.status == Attempt.Status.SUBMITTED:
        return attempt, False

    earned_points = Decimal("0")
    correct_count = 0
    answers = Answer.objects.filter(attempt=attempt).select_related("question", "selected_option")
    for answer in answers:
        if (
            answer.selected_option_id
            and answer.selected_option.question_id == answer.question_id
            and answer.selected_option.is_correct
        ):
            earned_points += answer.question.points
            correct_count += 1
    question_count = attempt.exam.questions.count()
    percentage = (
        Decimal(correct_count) * Decimal("100") / question_count
        if question_count
        else Decimal("0")
    )
    assessment = assess_attempt(attempt)
    attempt.score = earned_points.quantize(Decimal("0.01"))
    attempt.percentage = percentage.quantize(Decimal("0.01"))
    attempt.suspicion_score = assessment.score
    attempt.suspicion_level = assessment.level
    attempt.status = Attempt.Status.SUBMITTED
    attempt.submitted_at = timezone.now()
    attempt.save(
        update_fields=[
            "score",
            "percentage",
            "suspicion_score",
            "suspicion_level",
            "status",
            "submitted_at",
        ]
    )
    return attempt, True

def record_answer(attempt, question, option):
    if option.question_id != question.pk:
        raise ValueError("La opción no pertenece a esta pregunta.")
    if not Option.objects.filter(pk=option.pk, question=question).exists():
        raise ValueError("Opción no válida.")
    return Answer.objects.update_or_create(
        attempt=attempt,
        question=question,
        defaults={"selected_option": option},
    )
