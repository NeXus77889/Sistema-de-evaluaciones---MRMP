from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class Materia(models.Model):
    nombre = models.CharField(max_length=100)
    codigo = models.CharField(max_length=20, unique=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name_plural = "materias"

    def __str__(self):
        return self.nombre


class Curso(models.Model):
    nombre = models.CharField(max_length=100)
    codigo = models.CharField(max_length=20, unique=True)
    estudiantes = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="cursos",
        limit_choices_to={"rol": "ESTUDIANTE"},
    )

    class Meta:
        ordering = ["nombre"]
        verbose_name_plural = "cursos"

    @property
    def nombre_estandarizado(self):
        from apps.evaluaciones.academic import format_course_name
        return format_course_name(self.nombre, self.codigo)

    def __str__(self):
        from apps.evaluaciones.academic import format_course_name
        return format_course_name(self.nombre, self.codigo)


class AsignacionDocente(models.Model):
    docente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="asignaciones_docentes",
        limit_choices_to={"rol": "DOCENTE"},
    )
    materia = models.ForeignKey(Materia, on_delete=models.PROTECT, related_name="asignaciones")
    curso = models.ForeignKey(Curso, on_delete=models.PROTECT, related_name="asignaciones")
    activo = models.BooleanField(default=True)

    class Meta:
        unique_together = ("docente", "materia", "curso")
        verbose_name = "asignación docente"
        verbose_name_plural = "asignaciones docentes"

    def __str__(self):
        return f"{self.docente} - {self.materia} - {self.curso}"


class Exam(models.Model):
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_exams",
        limit_choices_to={"rol": "DOCENTE"},
    )
    materia = models.ForeignKey(Materia, on_delete=models.PROTECT, null=True)
    curso = models.ForeignKey(Curso, on_delete=models.PROTECT, null=True)
    cursos = models.ManyToManyField(
        Curso,
        blank=True,
        related_name="examenes",
    )
    students = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="assigned_exams",
        blank=True,
        limit_choices_to={"rol": "ESTUDIANTE"},
    )
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    duration_minutes = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    available_from = models.DateTimeField()
    available_until = models.DateTimeField(null=True, blank=True)
    published = models.BooleanField(default=False)
    results_visible = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-available_from", "title"]
        verbose_name = "evaluación"
        verbose_name_plural = "evaluaciones"
        constraints = [
            models.CheckConstraint(
                condition=Q(duration_minutes__gte=1),
                name="exam_duration_positive",
            ),
        ]

    def clean(self):
        if self.available_until and self.available_until <= self.available_from:
            raise ValidationError({"available_until": "Debe ser posterior al inicio."})
        if self.teacher_id and self.materia_id and self.curso_id:
            assigned = AsignacionDocente.objects.filter(
                docente=self.teacher,
                materia=self.materia,
                curso=self.curso,
                activo=True,
            ).exists()
            if not assigned:
                raise ValidationError(
                    "El docente no imparte esa materia en ese curso."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def is_assigned_to_student(self, student):
        if self.students.filter(pk=student.pk).exists():
            return True
        if self.curso_id and self.curso.estudiantes.filter(pk=student.pk).exists():
            return True
        return self.cursos.filter(estudiantes=student).exists()

    def __str__(self):
        return self.title


class Question(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()
    points = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=1,
        validators=[MinValueValidator(0.01)],
    )
    position = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["exam", "position"], name="unique_exam_question_position"),
            models.CheckConstraint(condition=Q(points__gt=0), name="question_points_positive"),
        ]

    def __str__(self):
        return f"{self.exam}: pregunta {self.position}"


class Option(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    text = models.CharField(max_length=1000)
    is_correct = models.BooleanField(default=False)
    position = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["question", "position"], name="unique_question_option_position"),
        ]

    def __str__(self):
        return self.text[:80]
