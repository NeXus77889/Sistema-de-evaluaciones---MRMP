from django.urls import path

from apps.core.views import (
    AccountPasswordChangeView,
    SignInView,
    SignOutView,
    create_support_ticket,
    dashboard,
    exam_delete,
    exam_edit,
    exam_import_preview,
    exam_launch,
    exam_results,
    exam_runner,
    report_download,
    result_detail,
    ticket_attention,
    ticket_password,
    ticket_user_info,
)

urlpatterns = [
    path("ingresar/", SignInView.as_view(), name="login"),
    path("salir/", SignOutView.as_view(), name="logout"),
    path("cambiar-password/", AccountPasswordChangeView.as_view(), name="password-change"),
    path(
        "clave/cambiar/",
        AccountPasswordChangeView.as_view(),
        name="password-change-legacy",
    ),
    path("api/tickets/", create_support_ticket, name="create-support-ticket"),
    path("secretaria/ticket/atender/", ticket_attention, name="ticket-attention"),
    path(
        "secretaria/ticket/<int:ticket_id>/contrasena/",
        ticket_password,
        name="ticket-password",
    ),
    path(
        "secretaria/ticket/<int:ticket_id>/usuario/",
        ticket_user_info,
        name="ticket-user-info",
    ),
    path("", dashboard, name="dashboard"),
    path("administracion/", dashboard, name="administracion"),
    path("docente/evaluacion/nueva/", exam_edit, name="exam-create"),
    path("docente/evaluacion/importar-docx/", exam_import_preview, name="exam-import-preview"),
    path("docente/evaluacion/<int:exam_id>/editar/", exam_edit, name="exam-edit"),
    path("docente/evaluacion/<int:exam_id>/resultados/", exam_results, name="exam-results"),
    path("docente/evaluacion/<int:exam_id>/eliminar/", exam_delete, name="exam-delete"),
    path("evaluacion/<int:exam_id>/preparar/", exam_launch, name="exam-launch"),
    path("intento/<int:attempt_id>/realizar/", exam_runner, name="exam-runner"),
    path("intento/<int:attempt_id>/resultado/", result_detail, name="result-detail"),
    path("intento/<int:attempt_id>/informe/", report_download, name="report-download"),
]