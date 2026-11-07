from django.contrib import admin
from django.utils import timezone

from apps.core.models import TicketAtencion
from .models import Answer, Attempt


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
    )
    readonly_fields = (
        "exam",
        "student",
        "status",
        "suspicion_score",
        "suspicion_level",
        "started_at",
        "submitted_at",
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