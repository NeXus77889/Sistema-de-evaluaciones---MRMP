from django.contrib import admin
from .models import LecturaMensaje, Mensaje


class LecturaMensajeInline(admin.TabularInline):
    model = LecturaMensaje
    extra = 0
    readonly_fields = ("destinatario", "leido", "fecha_lectura")
    can_delete = False


@admin.register(Mensaje)
class MensajeAdmin(admin.ModelAdmin):
    list_display = ("motivo", "remitente", "tipo_destino", "destinatario", "curso", "fecha")
    list_filter = ("tipo_destino", "fecha")
    search_fields = ("motivo", "cuerpo", "remitente__username", "remitente__first_name", "remitente__last_name")
    readonly_fields = ("fecha",)
    inlines = [LecturaMensajeInline]


@admin.register(LecturaMensaje)
class LecturaMensajeAdmin(admin.ModelAdmin):
    list_display = ("mensaje", "destinatario", "leido", "fecha_lectura")
    list_filter = ("leido",)
    search_fields = ("mensaje__motivo", "destinatario__username", "destinatario__first_name", "destinatario__last_name")

