from django.db import models


class AttemptReport(models.Model):
    attempt = models.OneToOneField(
        "intentos.Attempt",
        on_delete=models.PROTECT,
        related_name="report",
    )
    pdf = models.FileField(upload_to="private/reports/")
    created_at = models.DateTimeField(auto_now_add=True)
    email_attempted_at = models.DateTimeField(null=True, blank=True)
    email_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Informe intento {self.attempt_id}"
