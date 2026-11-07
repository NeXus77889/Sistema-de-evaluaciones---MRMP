from django.contrib import admin

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
        "creado_por",
        "creado_en",
        "atendido_por",
        "atendido_en",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.has_perm("core.view_ticketatencion")

    def has_delete_permission(self, request, obj=None):
        return False