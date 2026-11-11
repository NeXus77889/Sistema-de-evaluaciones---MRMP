from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from apps.usuarios.models import User
from .forms import MensajeAdminForm, MensajeDocenteForm, MensajeEstudianteForm
from .models import LecturaMensaje, Mensaje


@login_required
def inbox_view(request):
    """Bandeja de entrada: mensajes recibidos por el usuario actual."""
    lecturas_qs = (
        LecturaMensaje.objects.filter(destinatario=request.user)
        .select_related("mensaje", "mensaje__remitente", "mensaje__curso")
        .order_by("-mensaje__fecha")
    )

    q = request.GET.get("q", "").strip()
    if q:
        lecturas_qs = lecturas_qs.filter(
            Q(mensaje__motivo__icontains=q)
            | Q(mensaje__cuerpo__icontains=q)
            | Q(mensaje__remitente__first_name__icontains=q)
            | Q(mensaje__remitente__last_name__icontains=q)
            | Q(mensaje__remitente__username__icontains=q)
        )

    estado_filtro = request.GET.get("estado", "")
    if estado_filtro == "no_leido":
        lecturas_qs = lecturas_qs.filter(leido=False)
    elif estado_filtro == "leido":
        lecturas_qs = lecturas_qs.filter(leido=True)

    paginator = Paginator(lecturas_qs, 15)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    no_leidos_count = LecturaMensaje.objects.filter(
        destinatario=request.user, leido=False
    ).count()

    context = {
        "page_obj": page_obj,
        "q": q,
        "estado_filtro": estado_filtro,
        "no_leidos_count": no_leidos_count,
        "seccion_actual": "inbox",
    }
    return render(request, "mensajeria/inbox.html", context)


@login_required
def sent_view(request):
    """Mensajes enviados por el usuario actual."""
    mensajes_qs = (
        Mensaje.objects.filter(remitente=request.user)
        .select_related("destinatario", "curso")
        .order_by("-fecha")
    )

    q = request.GET.get("q", "").strip()
    if q:
        mensajes_qs = mensajes_qs.filter(
            Q(motivo__icontains=q)
            | Q(cuerpo__icontains=q)
            | Q(destinatario__first_name__icontains=q)
            | Q(destinatario__last_name__icontains=q)
            | Q(curso__nombre__icontains=q)
        )

    paginator = Paginator(mensajes_qs, 15)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "q": q,
        "seccion_actual": "sent",
    }
    return render(request, "mensajeria/sent.html", context)


@login_required
def detail_view(request, mensaje_id):
    """Detalle de un mensaje recibido o enviado."""
    mensaje = get_object_or_404(
        Mensaje.objects.select_related("remitente", "destinatario", "curso"),
        pk=mensaje_id,
    )

    es_remitente = mensaje.remitente_id == request.user.id
    lectura = LecturaMensaje.objects.filter(
        mensaje=mensaje, destinatario=request.user
    ).first()

    es_admin = request.user.rol == User.Role.ADMINISTRATOR

    if not (es_remitente or lectura or es_admin):
        return HttpResponseForbidden("No tienes permiso para ver este mensaje.")

    if lectura and not lectura.leido:
        lectura.marcar_leido()

    # Si es el remitente viendo un mensaje de curso, podemos mostrar estadísticas de lectura
    estadisticas_lectura = None
    if es_remitente and mensaje.tipo_destino == Mensaje.TIPO_CURSO:
        total_destinatarios = mensaje.lecturas.count()
        leidos = mensaje.lecturas.filter(leido=True).count()
        estadisticas_lectura = {
            "total": total_destinatarios,
            "leidos": leidos,
            "pendientes": total_destinatarios - leidos,
        }

    context = {
        "mensaje": mensaje,
        "es_remitente": es_remitente,
        "lectura": lectura,
        "estadisticas_lectura": estadisticas_lectura,
        "seccion_actual": "sent" if es_remitente else "inbox",
    }
    return render(request, "mensajeria/detail.html", context)


@login_required
def compose_view(request):
    """Redactar y enviar un nuevo mensaje."""
    user = request.user
    FormClass = MensajeDocenteForm

    if user.rol == User.Role.ADMINISTRATOR:
        FormClass = MensajeAdminForm
    elif user.rol == User.Role.STUDENT:
        FormClass = MensajeEstudianteForm

    initial_data = {}
    reply_to_id = request.GET.get("reply_to")
    if reply_to_id and request.method == "GET":
        try:
            original = Mensaje.objects.get(pk=reply_to_id)
            if original.remitente_id != user.id:
                initial_data["destinatario"] = original.remitente_id
                initial_data["tipo_destino"] = Mensaje.TIPO_INDIVIDUAL
                prefijo = "Re: " if not original.motivo.startswith("Re: ") else ""
                initial_data["motivo"] = f"{prefijo}{original.motivo}"
        except Mensaje.DoesNotExist:
            pass

    if request.method == "POST":
        form = FormClass(request.POST, request.FILES, user=user)
        if form.is_valid():
            nuevo_mensaje = form.save(commit=False)
            nuevo_mensaje.remitente = user
            nuevo_mensaje.save()
            messages.success(request, "¡Mensaje enviado con éxito!")
            return redirect("mensajeria:sent")
    else:
        form = FormClass(user=user, initial=initial_data)

    context = {
        "form": form,
        "seccion_actual": "compose",
    }
    return render(request, "mensajeria/compose.html", context)

