from django.conf import settings
from django.db import models


class TicketAtencion(models.Model):
    class Tipo(models.TextChoices):
        PASSWORD = "PASS", "Recuperar contraseña"
        USER = "USER", "Recuperar usuario o cédula"
        EXAM = "EXAM", "Consulta de evaluación"
        PROCTOR = "PROCTOR", "Incidencia de proctoring"

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        RESUELTO = "RESUELTO", "Resuelto"

    codigo = models.CharField(max_length=80, db_index=True)
    tipo = models.CharField(max_length=8, choices=Tipo.choices)
    estado = models.CharField(
        max_length=10,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
        db_index=True,
    )
    correo_contacto = models.EmailField(blank=True)
    estudiante = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tickets_atencion",
    )
    intento = models.ForeignKey(
        "intentos.Attempt",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tickets_atencion",
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tickets_creados",
    )
    atendido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tickets_atendidos",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    atendido_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado_en", "-pk"]
        indexes = [models.Index(fields=["tipo", "estado"])]
        verbose_name = "ticket de atención"
        verbose_name_plural = "tickets de atención"

    def __str__(self):
        return f"{self.codigo} ({self.get_estado_display()})"