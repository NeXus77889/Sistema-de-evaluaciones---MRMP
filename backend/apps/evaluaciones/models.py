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
    aprobada = models.BooleanField(
        default=False,
        verbose_name="Aprobada por Administrador",
        help_text="Indica si la evaluación ha sido revisada y aprobada por la administración.",
    )
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


class Tarea(models.Model):
    TRIMESTRE_1 = 1
    TRIMESTRE_2 = 2
    TRIMESTRE_3 = 3
    TRIMESTRES = [
        (TRIMESTRE_1, "Primer Trimestre"),
        (TRIMESTRE_2, "Segundo Trimestre"),
        (TRIMESTRE_3, "Tercer Trimestre"),
    ]

    PARCIAL_1 = 1
    PARCIAL_2 = 2
    PARCIALES = [
        (PARCIAL_1, "Primer Parcial"),
        (PARCIAL_2, "Segundo Parcial"),
    ]

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
    trimestre = models.PositiveSmallIntegerField(
        choices=TRIMESTRES,
        default=1,
        help_text="Trimestre al que pertenece la tarea (1, 2 o 3)",
    )
    parcial = models.PositiveSmallIntegerField(
        choices=PARCIALES,
        default=1,
        help_text="Parcial al que pertenece la tarea (1 o 2)",
    )
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
            if getattr(self.docente, "rol", "") == "DOCENTE" and not getattr(self.docente, "is_superuser", False):
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

    def asegurar_insumo(self):
        insumo = getattr(self, "insumo", None)
        nombre_insumo = f"Tarea: {self.titulo}"
        if insumo is None:
            insumo, _ = InsumoCalificacion.objects.get_or_create(
                tarea=self,
                defaults={
                    "curso": self.curso,
                    "materia": self.materia,
                    "docente": self.docente,
                    "nombre": nombre_insumo,
                    "tipo": InsumoCalificacion.TIPO_INSUMO_1,
                    "trimestre": self.trimestre,
                    "parcial": self.parcial,
                    "periodo": f"Trimestre {self.trimestre} - Parcial {self.parcial}",
                    "ponderacion": self.peso_porcentual,
                    "publicado": self.activo,
                },
            )
        else:
            updated = False
            if insumo.nombre != nombre_insumo:
                insumo.nombre = nombre_insumo
                updated = True
            if insumo.trimestre != self.trimestre or insumo.parcial != self.parcial:
                insumo.trimestre = self.trimestre
                insumo.parcial = self.parcial
                insumo.periodo = f"Trimestre {self.trimestre} - Parcial {self.parcial}"
                updated = True
            if insumo.ponderacion != self.peso_porcentual:
                insumo.ponderacion = self.peso_porcentual
                updated = True
            if insumo.curso_id != self.curso_id or insumo.materia_id != self.materia_id:
                insumo.curso = self.curso
                insumo.materia = self.materia
                updated = True
            if insumo.publicado != self.activo:
                insumo.publicado = self.activo
                updated = True
            if updated:
                insumo.save()
        return insumo

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        self.asegurar_insumo()

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

        if self.tarea_id and self.estudiante_id:
            insumo = self.tarea.asegurar_insumo()
            if self.calificacion is not None:
                RegistroCalificacion.objects.update_or_create(
                    insumo=insumo,
                    estudiante=self.estudiante,
                    defaults={"nota": self.calificacion},
                )
            else:
                RegistroCalificacion.objects.filter(
                    insumo=insumo,
                    estudiante=self.estudiante,
                ).delete()

    def __str__(self):
        return f"{self.tarea.titulo} - {self.estudiante} ({self.get_estado_display()})"


class InsumoCalificacion(models.Model):
    TIPO_INSUMO_1 = "INSUMO_1"
    TIPO_INSUMO_2 = "INSUMO_2"
    TIPO_EVALUACION = "EVALUACION"
    TIPO_EXAMEN_FINAL = "EXAMEN_FINAL"
    TIPOS = [
        (TIPO_INSUMO_1, "Insumo 1 (Tareas / Actividades individuales)"),
        (TIPO_INSUMO_2, "Insumo 2 (Lecciones / Proyectos grupales)"),
        (TIPO_EVALUACION, "Evaluación Parcial"),
        (TIPO_EXAMEN_FINAL, "Examen Final"),
    ]

    TRIMESTRE_1 = 1
    TRIMESTRE_2 = 2
    TRIMESTRE_3 = 3
    TRIMESTRES = [
        (TRIMESTRE_1, "Primer Trimestre"),
        (TRIMESTRE_2, "Segundo Trimestre"),
        (TRIMESTRE_3, "Tercer Trimestre"),
    ]

    PARCIAL_1 = 1
    PARCIAL_2 = 2
    PARCIALES = [
        (PARCIAL_1, "Primer Parcial"),
        (PARCIAL_2, "Segundo Parcial"),
    ]

    curso = models.ForeignKey(Curso, on_delete=models.CASCADE, related_name="insumos_calificacion")
    materia = models.ForeignKey(Materia, on_delete=models.CASCADE, related_name="insumos_calificacion")
    docente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="insumos_docente",
        limit_choices_to={"rol": "DOCENTE"},
    )
    tarea = models.OneToOneField(
        Tarea,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="insumo",
    )
    nombre = models.CharField(max_length=150)
    tipo = models.CharField(max_length=20, choices=TIPOS, default=TIPO_INSUMO_1)
    trimestre = models.PositiveSmallIntegerField(
        choices=TRIMESTRES,
        default=1,
        help_text="Trimestre (1, 2 o 3)",
    )
    parcial = models.PositiveSmallIntegerField(
        choices=PARCIALES,
        default=1,
        help_text="Parcial (1 o 2)",
    )
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
            if getattr(self.docente, "rol", "") == "DOCENTE" and not getattr(self.docente, "is_superuser", False):
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
        if self.insumo_id and self.insumo.tarea_id:
            entrega, created = EntregaTarea.objects.get_or_create(
                tarea_id=self.insumo.tarea_id,
                estudiante=self.estudiante,
                defaults={"calificacion": self.nota},
            )
            if not created and entrega.calificacion != self.nota:
                entrega.calificacion = self.nota
                entrega.fecha_calificacion = timezone.now()
                entrega.save(update_fields=["calificacion", "fecha_calificacion"])

    def delete(self, *args, **kwargs):
        tarea_id = self.insumo.tarea_id if self.insumo_id else None
        estudiante = self.estudiante
        super().delete(*args, **kwargs)
        if tarea_id:
            EntregaTarea.objects.filter(
                tarea_id=tarea_id,
                estudiante=estudiante,
            ).update(calificacion=None, fecha_calificacion=None)

    def __str__(self):
        return f"{self.estudiante}: {self.nota} ({self.insumo.nombre})"


class ControlParcial(models.Model):
    TRIMESTRE_1 = 1
    TRIMESTRE_2 = 2
    TRIMESTRE_3 = 3
    TRIMESTRES = [
        (TRIMESTRE_1, "Primer Trimestre"),
        (TRIMESTRE_2, "Segundo Trimestre"),
        (TRIMESTRE_3, "Tercer Trimestre"),
    ]

    PARCIAL_1 = 1
    PARCIAL_2 = 2
    PARCIALES = [
        (PARCIAL_1, "Primer Parcial"),
        (PARCIAL_2, "Segundo Parcial"),
    ]

    trimestre = models.PositiveSmallIntegerField(
        choices=TRIMESTRES,
        default=TRIMESTRE_1,
        help_text="Trimestre académico (1, 2 o 3)",
    )
    parcial = models.PositiveSmallIntegerField(
        choices=PARCIALES,
        default=PARCIAL_1,
        help_text="Parcial académico (1 o 2)",
    )
    habilitado = models.BooleanField(
        default=False,
        help_text="Si está habilitado, los docentes pueden calificar este parcial. Si está desactivado, el parcial está cerrado o finalizado.",
    )
    finalizado_en = models.DateTimeField(null=True, blank=True)
    observacion = models.CharField(max_length=255, blank=True)
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="parciales_gestionados",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("trimestre", "parcial")
        ordering = ["trimestre", "parcial"]
        verbose_name = "control de parcial"
        verbose_name_plural = "control de parciales"

    def __str__(self):
        estado = "Habilitado" if self.habilitado else "Finalizado / Bloqueado"
        return f"Trimestre {self.trimestre} - Parcial {self.parcial} ({estado})"

    @classmethod
    def es_habilitado(cls, trimestre, parcial):
        """
        Devuelve True si el parcial especificado está habilitado para calificaciones.
        Si aún no hay registros creados en la base de datos, por defecto el Trimestre 1 Parcial 1
        está habilitado y el resto finalizados/cerrados.
        """
        try:
            registro = cls.objects.filter(trimestre=int(trimestre), parcial=int(parcial)).first()
            if registro is not None:
                return bool(registro.habilitado)
            return int(trimestre) == 1 and int(parcial) == 1
        except Exception:
            return int(trimestre) == 1 and int(parcial) == 1

    @classmethod
    def obtener_todos(cls):
        """
        Devuelve una lista con los 6 parciales estándar (T1P1 a T3P2),
        garantizando que existan registros o defaults.
        """
        resultados = []
        parciales_info = [
            (1, 1, "Primer Trimestre - Primer Parcial"),
            (1, 2, "Primer Trimestre - Segundo Parcial"),
            (2, 1, "Segundo Trimestre - Primer Parcial"),
            (2, 2, "Segundo Trimestre - Segundo Parcial"),
            (3, 1, "Tercer Trimestre - Primer Parcial"),
            (3, 2, "Tercer Trimestre - Segundo Parcial"),
        ]
        try:
            existentes = {
                (cp.trimestre, cp.parcial): cp
                for cp in cls.objects.all()
            }
        except Exception:
            existentes = {}

        for trim, parc, nombre in parciales_info:
            reg = existentes.get((trim, parc))
            if reg:
                resultados.append({
                    "trimestre": trim,
                    "parcial": parc,
                    "nombre": nombre,
                    "habilitado": reg.habilitado,
                    "finalizado_en": reg.finalizado_en,
                    "observacion": reg.observacion,
                    "instancia": reg,
                })
            else:
                es_def_hab = (trim == 1 and parc == 1)
                resultados.append({
                    "trimestre": trim,
                    "parcial": parc,
                    "nombre": nombre,
                    "habilitado": es_def_hab,
                    "finalizado_en": None,
                    "observacion": "",
                    "instancia": None,
                })
        return resultados

