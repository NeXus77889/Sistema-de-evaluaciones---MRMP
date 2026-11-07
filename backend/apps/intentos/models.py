from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class Attempt(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "En curso"
        SUBMITTED = "submitted", "Entregado"

    exam = models.ForeignKey("evaluaciones.Exam", on_delete=models.PROTECT, related_name="attempts")
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="attempts",
        limit_choices_to={"rol": "ESTUDIANTE"},
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.IN_PROGRESS)
    started_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    score = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    suspicion_score = models.PositiveSmallIntegerField(null=True, blank=True)
    suspicion_level = models.CharField(max_length=8, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "intento de evaluación"
        verbose_name_plural = "intentos de evaluación"
        constraints = [
            models.UniqueConstraint(fields=["exam", "student"], name="one_attempt_per_exam_student"),
            models.CheckConstraint(
                condition=Q(suspicion_score__isnull=True) | Q(suspicion_score__lte=100),
                name="attempt_suspicion_score_lte_100",
            ),
        ]

    @property
    def deadline(self):
        from datetime import timedelta

        return self.started_at + timedelta(minutes=self.exam.duration_minutes)

    def __str__(self):
        return f"{self.student} - {self.exam}"


class Answer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey("evaluaciones.Question", on_delete=models.PROTECT, related_name="answers")
    selected_option = models.ForeignKey(
        "evaluaciones.Option",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="selected_answers",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["attempt", "question"], name="one_answer_per_question")]

    def __str__(self):
        return f"{self.attempt}: {self.question}"


class Incident(models.Model):
    class Kind(models.TextChoices):
        TAB_HIDDEN = "tab_hidden", "Pestaña no visible"
        WINDOW_BLUR = "window_blur", "Pérdida de foco"
        CAMERA_LOST = "camera_lost", "Cámara desconectada"
        MICROPHONE_LOST = "microphone_lost", "Micrófono desconectado"
        CAMERA_MUTED = "camera_muted", "Cámara desactivada"
        MICROPHONE_MUTED = "microphone_muted", "Micrófono desactivado"

    class Severity(models.TextChoices):
        LOW = "low", "Baja"
        MEDIUM = "medium", "Media"
        HIGH = "high", "Alta"

    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="incidents")
    kind = models.CharField(max_length=24, choices=Kind.choices)
    occurred_at = models.DateTimeField(auto_now_add=True)
    duration_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MaxValueValidator(86_400_000)],
    )
    description = models.CharField(max_length=240)
    severity = models.CharField(max_length=8, choices=Severity.choices)
    client_event_id = models.UUIDField(null=True, blank=True, unique=True)

    class Meta:
        ordering = ["occurred_at", "id"]
        indexes = [models.Index(fields=["attempt", "kind"])]

    def __str__(self):
        return f"{self.get_kind_display()} ({self.occurred_at:%Y-%m-%d %H:%M:%S})"
