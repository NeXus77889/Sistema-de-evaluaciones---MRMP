import os
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

# ==============================================================================
# CONFIGURACIÓN DE POLÍTICAS DE MENSAJERÍA
# ==============================================================================
# Habilitar después para permitir que los estudiantes contacten a personal administrativo
ESTUDIANTE_PUEDE_ESCRIBIR_A_ADMINISTRATIVOS = False

# Extensiones y tipos de archivo permitidos para adjuntos
EXTENSIONES_PERMITIDAS = {
    "pdf",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp",
    "docx",
    "xlsx",
}
MAX_ADJUNTO_BYTES = 5 * 1024 * 1024  # 5 MB


def validar_adjunto_mensajeria(archivo):
    if not archivo:
        return
    if archivo.size > MAX_ADJUNTO_BYTES:
        raise ValidationError("El archivo adjunto no puede exceder 5 MB.")
    ext = os.path.splitext(archivo.name)[1].lower().lstrip(".")
    if ext not in EXTENSIONES_PERMITIDAS:
        raise ValidationError(
            f"Tipo de archivo no permitido (.{ext}). "
            f"Tipos autorizados: PDF, imágenes (JPG, PNG, WEBP), Word (DOCX) y Excel (XLSX)."
        )


class Mensaje(models.Model):
    TIPO_INDIVIDUAL = "INDIVIDUAL"
    TIPO_CURSO = "CURSO"
    TIPOS_DESTINO = [
        (TIPO_INDIVIDUAL, "Individual"),
        (TIPO_CURSO, "Curso completo"),
    ]

    remitente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mensajes_enviados",
    )
    tipo_destino = models.CharField(
        max_length=20,
        choices=TIPOS_DESTINO,
        default=TIPO_INDIVIDUAL,
    )
    destinatario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mensajes_directos_recibidos",
    )
    curso = models.ForeignKey(
        "evaluaciones.Curso",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mensajes_curso",
    )
    motivo = models.CharField(max_length=200, verbose_name="Asunto / Motivo")
    cuerpo = models.TextField(verbose_name="Mensaje")
    adjunto = models.FileField(
        upload_to="mensajeria/%Y/%m/",
        null=True,
        blank=True,
        validators=[validar_adjunto_mensajeria],
        help_text="Opcional. Límite 5 MB (PDF, imágenes, Word, Excel).",
    )
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "comunicado / mensaje"
        verbose_name_plural = "mensajes"

    def clean(self):
        super().clean()
        if self.tipo_destino == self.TIPO_INDIVIDUAL and not self.destinatario_id:
            raise ValidationError({"destinatario": "Debes especificar un destinatario individual."})
        if self.tipo_destino == self.TIPO_CURSO and not self.curso_id:
            raise ValidationError({"curso": "Debes especificar el curso de destino."})

    def crear_lecturas(self):
        """Crea los registros de lectura para cada destinatario del mensaje."""
        if self.tipo_destino == self.TIPO_INDIVIDUAL and self.destinatario_id:
            LecturaMensaje.objects.get_or_create(
                mensaje=self,
                destinatario=self.destinatario,
            )
        elif self.tipo_destino == self.TIPO_CURSO and self.curso_id:
            estudiantes = self.curso.estudiantes.filter(is_active=True)
            lecturas = [
                LecturaMensaje(mensaje=self, destinatario=est, leido=False)
                for est in estudiantes
            ]
            LecturaMensaje.objects.bulk_create(lecturas, ignore_conflicts=True)

    def save(self, *args, **kwargs):
        self.full_clean()
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            self.crear_lecturas()

    def __str__(self):
        return f"{self.motivo} ({self.remitente} -> {self.destinatario or self.curso})"


class LecturaMensaje(models.Model):
    mensaje = models.ForeignKey(
        Mensaje,
        on_delete=models.CASCADE,
        related_name="lecturas",
    )
    destinatario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="lecturas_mensajes",
    )
    leido = models.BooleanField(default=False)
    fecha_lectura = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("mensaje", "destinatario")
        ordering = ["-mensaje__fecha"]
        verbose_name = "lectura de mensaje"
        verbose_name_plural = "lecturas de mensajes"

    def marcar_leido(self):
        if not self.leido:
            self.leido = True
            self.fecha_lectura = timezone.now()
            self.save(update_fields=["leido", "fecha_lectura"])

    def __str__(self):
        estado = "Leído" if self.leido else "No leído"
        return f"{self.destinatario}: {self.mensaje.motivo} ({estado})"

