from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


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
            models.CheckConstraint(check=Q(points__gt=0), name="question_points_positive"),
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


class Tarea(models.Model):
    curso = models.ForeignKey(Curso, on_delete=models.CASCADE, related_name="tareas")
    materia = models.ForeignKey(Materia, on_delete=models.CASCADE, related_name="tareas")
    docente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="tareas_docente",
        limit_choices_to={"rol": "DOCENTE"},
    )
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    fecha_entrega = models.DateTimeField()
    peso_porcentual = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10.00,
        validators=[MinValueValidator(0.01), MaxValueValidator(100.00)],
        help_text="Peso porcentual de la tarea (0.01 - 100.00%)",
    )
    archivo_adjunto = models.FileField(
        upload_to="tareas/adjuntos/%Y/%m/",
        blank=True,
        null=True,
        help_text="Material o guía adjunta para la tarea",
    )
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha_entrega", "titulo"]
        verbose_name = "tarea"
        verbose_name_plural = "tareas"

    def clean(self):
        if self.docente_id and self.materia_id and self.curso_id:
            assigned = AsignacionDocente.objects.filter(
                docente=self.docente,
                materia=self.materia,
                curso=self.curso,
                activo=True,
            ).exists()
            if not assigned:
                raise ValidationError(
                    "El docente no tiene asignación activa para dictar esta materia en este curso."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.titulo} - {self.curso} ({self.materia})"


class EntregaTarea(models.Model):
    ESTADO_PENDIENTE = "PENDIENTE"
    ESTADO_ENTREGADO = "ENTREGADO"
    ESTADO_ATRASADO = "ATRASADO"
    ESTADOS = [
        (ESTADO_PENDIENTE, "Pendiente"),
        (ESTADO_ENTREGADO, "Entregado"),
        (ESTADO_ATRASADO, "Atrasado"),
    ]

    tarea = models.ForeignKey(Tarea, on_delete=models.CASCADE, related_name="entregas")
    estudiante = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="entregas_tareas",
        limit_choices_to={"rol": "ESTUDIANTE"},
    )
    archivo = models.FileField(
        upload_to="tareas/entregas/%Y/%m/",
        blank=True,
        null=True,
    )
    comentario = models.TextField(blank=True)
    fecha_subida = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default=ESTADO_PENDIENTE,
    )
    calificacion = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0.00), MaxValueValidator(10.00)],
    )
    retroalimentacion = models.TextField(blank=True)
    fecha_calificacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("tarea", "estudiante")
        ordering = ["-fecha_subida"]
        verbose_name = "entrega de tarea"
        verbose_name_plural = "entregas de tareas"

    def clean(self):
        if self.tarea_id and self.estudiante_id:
            if not self.tarea.curso.estudiantes.filter(pk=self.estudiante_id).exists():
                raise ValidationError("El estudiante no pertenece al curso de esta tarea.")

    def save(self, *args, **kwargs):
        if self.archivo:
            now = timezone.now()
            if self.tarea.fecha_entrega and now > self.tarea.fecha_entrega:
                self.estado = self.ESTADO_ATRASADO
            else:
                self.estado = self.ESTADO_ENTREGADO
        elif not self.estado:
            self.estado = self.ESTADO_PENDIENTE

        if self.calificacion is not None and not self.fecha_calificacion:
            self.fecha_calificacion = timezone.now()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.tarea.titulo} - {self.estudiante} ({self.get_estado_display()})"


class InsumoCalificacion(models.Model):
    TIPO_INSUMO_1 = "INSUMO_1"
    TIPO_INSUMO_2 = "INSUMO_2"
    TIPO_EVALUACION = "EVALUACION"
    TIPOS = [
        (TIPO_INSUMO_1, "Insumo 1 (Tareas / Actividades individuales)"),
        (TIPO_INSUMO_2, "Insumo 2 (Lecciones / Proyectos grupales)"),
        (TIPO_EVALUACION, "Evaluación Parcial"),
    ]

    curso = models.ForeignKey(Curso, on_delete=models.CASCADE, related_name="insumos_calificacion")
    materia = models.ForeignKey(Materia, on_delete=models.CASCADE, related_name="insumos_calificacion")
    docente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="insumos_docente",
        limit_choices_to={"rol": "DOCENTE"},
    )
    nombre = models.CharField(max_length=150)
    tipo = models.CharField(max_length=20, choices=TIPOS, default=TIPO_INSUMO_1)
    periodo = models.CharField(max_length=80, default="Primer Quimestre - Parcial 1")
    ponderacion = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=35.00,
        validators=[MinValueValidator(0.01), MaxValueValidator(100.00)],
        help_text="Porcentaje de peso para el promedio final del parcial (ej. 35.00)",
    )
    publicado = models.BooleanField(
        default=False,
        help_text="Hacer visible estas calificaciones en el portal de los estudiantes",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["curso", "materia", "tipo", "created_at"]
        verbose_name = "insumo de calificación"
        verbose_name_plural = "insumos de calificación"

    def clean(self):
        if self.docente_id and self.materia_id and self.curso_id:
            assigned = AsignacionDocente.objects.filter(
                docente=self.docente,
                materia=self.materia,
                curso=self.curso,
                activo=True,
            ).exists()
            if not assigned:
                raise ValidationError(
                    "El docente no tiene asignación activa para dictar esta materia en este curso."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_display()}) - {self.curso} [{self.materia}]"


class RegistroCalificacion(models.Model):
    insumo = models.ForeignKey(
        InsumoCalificacion,
        on_delete=models.CASCADE,
        related_name="registros",
    )
    estudiante = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="calificaciones",
        limit_choices_to={"rol": "ESTUDIANTE"},
    )
    nota = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        validators=[MinValueValidator(0.00), MaxValueValidator(10.00)],
        help_text="Nota sobre 10.00",
    )
    observacion = models.CharField(max_length=255, blank=True)
    fecha_registro = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("insumo", "estudiante")
        ordering = ["estudiante__last_name", "estudiante__first_name"]
        verbose_name = "registro de calificación"
        verbose_name_plural = "registros de calificaciones"

    def clean(self):
        if self.insumo_id and self.estudiante_id:
            if not self.insumo.curso.estudiantes.filter(pk=self.estudiante_id).exists():
                raise ValidationError("El estudiante no pertenece al curso correspondiente a este insumo.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.estudiante}: {self.nota} ({self.insumo.nombre})"
