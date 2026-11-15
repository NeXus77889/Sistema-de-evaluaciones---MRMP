from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import TicketAtencion


@admin.register(TicketAtencion)
class TicketAtencionAdmin(admin.ModelAdmin):
    list_display = (
        "codigo",
        "tipo",
        "estado",
        "estudiante",
        "creado_en",
        "atendido_por",
        "atendido_en",
    )
    list_filter = ("tipo", "estado", "creado_en")
    search_fields = ("codigo", "estudiante__identification", "estudiante__email")
    readonly_fields = (
        "codigo",
        "tipo",
        "estado",
        "correo_contacto",
        "estudiante",
        "intento",
        "informe_asociado",
        "creado_por",
        "creado_en",
        "atendido_por",
        "atendido_en",
    )

    @admin.display(description="Informe de intento")
    def informe_asociado(self, ticket):
        if ticket.intento_id:
            url = reverse("report-download", args=[ticket.intento_id])
            return format_html(
                '<a class="button" href="{}" target="_blank" style="white-space:nowrap;display:inline-flex;align-items:center;justify-content:center;padding:6px 14px;font-size:11px;font-weight:700;line-height:1.2;text-decoration:none;border-radius:8px;">Descargar informe del intento</a>',
                url,
            )
        return "Este ticket no está asociado a un intento de evaluación."

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.has_perm("core.view_ticketatencion")

    def has_delete_permission(self, request, obj=None):
        return False