from django.urls import path
from . import views

app_name = "mensajeria"

urlpatterns = [
    path("", views.inbox_view, name="inbox"),
    path("enviados/", views.sent_view, name="sent"),
    path("nuevo/", views.compose_view, name="compose"),
    path("<int:mensaje_id>/", views.detail_view, name="detail"),
]

