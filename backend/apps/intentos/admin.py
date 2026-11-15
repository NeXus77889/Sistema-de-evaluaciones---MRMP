from django.contrib import admin
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from apps.core.models import TicketAtencion
from .models import Answer, Attempt, Incident


class AnswerReviewInline(admin.TabularInline):
    model = Answer
    extra = 0
    can_delete = False
    fields = ("question", "selected_option")
    readonly_fields = ("question", "selected_option")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    inlines = (AnswerReviewInline,)
    list_display = (
        "id",
        "exam_title",
        "student_name",
        "status_label",
        "score",
        "percentage",
        "started_at",
        "informe_pdf",
    )
    list_filter = ("status", "exam")
    search_fields = (
        "student__identification",
        "student__username",
        "student__first_name",
        "student__last_name",
        "exam__title",
    )
    fields = (
        "exam",
        "student",
        "status",
        "score",
        "percentage",
        "suspicion_score",
        "suspicion_level",
        "started_at",
        "submitted_at",
        "informe_pdf",
    )
    readonly_fields = (
        "exam",
        "student",
        "status",
        "suspicion_score",
        "suspicion_level",
        "started_at",
        "submitted_at",
        "informe_pdf",
    )

    @admin.display(description="Evaluación", ordering="exam__title")
    def exam_title(self, attempt):
        return attempt.exam.title

    @admin.display(description="Estudiante", ordering="student__username")
    def student_name(self, attempt):
        return attempt.student.get_full_name() or attempt.student.username

    @admin.display(description="Estado", ordering="status")
    def status_label(self, attempt):
        return attempt.get_status_display()

    @admin.display(description="Informe PDF")
    def informe_pdf(self, attempt):
        if not attempt or not attempt.pk:
            return "—"
        url = reverse("report-download", args=[attempt.pk])
        return format_html(
            '<a class="button" href="{}" target="_blank" style="white-space:nowrap;display:inline-flex;align-items:center;justify-content:center;padding:6px 14px;font-size:11px;font-weight:700;line-height:1.2;text-decoration:none;border-radius:8px;">Descargar PDF</a>',
            url,
        )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        TicketAtencion.objects.filter(
            intento=obj,
            estado=TicketAtencion.Estado.PENDIENTE,
        ).update(
            estado=TicketAtencion.Estado.RESUELTO,
            atendido_por=request.user,
            atendido_en=timezone.now(),
        )


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "kind_label",
        "student_name",
        "exam_title",
        "occurred_at",
        "severity_badge",
    )
    list_filter = ("kind", "severity", "occurred_at")
    search_fields = (
        "attempt__student__identification",
        "attempt__student__username",
        "attempt__student__first_name",
        "attempt__student__last_name",
        "attempt__exam__title",
        "description",
    )
    readonly_fields = ("attempt", "kind", "occurred_at", "duration_ms", "description", "severity", "client_event_id")

    @admin.display(description="Evento")
    def kind_label(self, incident):
        return incident.get_kind_display()

    @admin.display(description="Estudiante")
    def student_name(self, incident):
        student = incident.attempt.student
        return student.get_full_name() or student.username

    @admin.display(description="Evaluación")
    def exam_title(self, incident):
        return incident.attempt.exam.title

    @admin.display(description="Gravedad")
    def severity_badge(self, incident):
        colors = {
            Incident.Severity.LOW: "#64748b",
            Incident.Severity.MEDIUM: "#d97706",
            Incident.Severity.HIGH: "#dc2626",
        }
        color = colors.get(incident.severity, "#64748b")
        return format_html(
            '<span style="font-weight:700; color: {};">{}</span>',
            color,
            incident.get_severity_display(),
        )
