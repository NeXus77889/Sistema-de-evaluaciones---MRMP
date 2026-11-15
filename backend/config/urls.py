from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

admin.site.site_header = "Administración Sistema Proctoring — UEPMRMP"
admin.site.site_title = "Sistema Proctoring — UEPMRMP"
admin.site.index_title = "Panel de Control Institucional"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", RedirectView.as_view(pattern_name="login", permanent=False)),
    path("", include("apps.core.urls")),
    path("mensajes/", include("apps.mensajeria.urls")),
    path("api/evaluaciones/", include("apps.intentos.urls")),
]
