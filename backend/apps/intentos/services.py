from decimal import Decimal

from django.db import transaction
from django.db.models import Sum    answers = Answer.objects.filter(attempt=attempt).select_related("question", "selected_option")
    for answer in answers:
        if (
            answer.selected_option_id
            and answer.selected_option.question_id == answer.question_id
            and answer.selected_option.is_correct
        ):
            earned_points += answer.question.points
    total_points = attempt.exam.questions.aggregate(total=Sum("points"))["total"] or Decimal("0")
    percentage = (
        earned_points * Decimal("100") / total_points
        if total_points        else Decimal("0")
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
    from apps.evaluaciones.grading import sync_online_exam_attempt

    sync_online_exam_attempt(attempt)
    return attempt, True

def record_answer(attempt, question, option):
    if option.question_id != question.pk:
        raise ValueError("La opciÃ³n no pertenece a esta pregunta.")
    if not Option.objects.filter(pk=option.pk, question=question).exists():
        raise ValueError("OpciÃ³n no vÃ¡lida.")
    return Answer.objects.update_or_create(
        attempt=attempt,
        question=question,
        defaults={"selected_option": option},
    )
