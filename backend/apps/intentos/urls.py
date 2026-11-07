from django.urls import path

from apps.intentos.views import (
    AttemptStateView,
    RecordIncidentView,
    SaveAnswerView,
    StartAttemptView,
    SubmitAttemptView,
)

urlpatterns = [
    path("<int:exam_id>/iniciar/", StartAttemptView.as_view(), name="attempt-start"),
    path("intento/<int:attempt_id>/", AttemptStateView.as_view(), name="attempt-state"),
    path("intento/<int:attempt_id>/respuesta/", SaveAnswerView.as_view(), name="attempt-answer"),
    path("intento/<int:attempt_id>/incidencias/", RecordIncidentView.as_view(), name="attempt-incident"),
    path("intento/<int:attempt_id>/entregar/", SubmitAttemptView.as_view(), name="attempt-submit"),
]