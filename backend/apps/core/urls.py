from django.urls import path

from apps.core.views import (
    AccountPasswordChangeView,
    SignInView,
    SignOutView,
    admin_toggle_aprobacion_evaluacion,
    admin_toggle_parcial,
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
from apps.evaluaciones.task_views import (
    docente_calificaciones_matrix,
    docente_tarea_detalle,
    docente_tarea_form,
    docente_tareas_list,
    estudiante_calificaciones_boletin,
    estudiante_tarea_entrega,
    estudiante_tareas_list,
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
    path("administracion/parciales/toggle/", admin_toggle_parcial, name="admin-toggle-parcial"),
    path("administracion/evaluacion/<int:exam_id>/aprobar/", admin_toggle_aprobacion_evaluacion, name="admin-toggle-aprobacion-evaluacion"),
    path("docente/evaluacion/nueva/", exam_edit, name="exam-create"),
    path("docente/evaluacion/importar-docx/", exam_import_preview, name="exam-import-preview"),
    path("docente/evaluacion/<int:exam_id>/editar/", exam_edit, name="exam-edit"),
    path("docente/evaluacion/<int:exam_id>/resultados/", exam_results, name="exam-results"),
    path("docente/evaluacion/<int:exam_id>/eliminar/", exam_delete, name="exam-delete"),
    path("evaluacion/<int:exam_id>/preparar/", exam_launch, name="exam-launch"),
    path("intento/<int:attempt_id>/realizar/", exam_runner, name="exam-runner"),
    path("intento/<int:attempt_id>/resultado/", result_detail, name="result-detail"),
    path("intento/<int:attempt_id>/informe/", report_download, name="report-download"),
    # Módulo de Tareas y Entregas (Docente)
    path("docente/tareas/", docente_tareas_list, name="docente-tareas-list"),
    path("docente/tareas/nueva/", docente_tarea_form, name="docente-tarea-create"),
    path("docente/tareas/<int:tarea_id>/", docente_tarea_detalle, name="docente-tarea-detalle"),
    path("docente/tareas/<int:tarea_id>/editar/", docente_tarea_form, name="docente-tarea-edit"),
    # Módulo de Calificaciones Institucional (Docente)
    path("docente/calificaciones/", docente_calificaciones_matrix, name="docente-calificaciones-matrix"),
    # Portal Estudiante
    path("estudiante/tareas/", estudiante_tareas_list, name="estudiante-tareas-list"),
    path("estudiante/tareas/<int:tarea_id>/entregar/", estudiante_tarea_entrega, name="estudiante-tarea-entrega"),
    path("estudiante/calificaciones/", estudiante_calificaciones_boletin, name="estudiante-calificaciones-boletin"),
]