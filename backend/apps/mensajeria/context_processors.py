from .models import LecturaMensaje


def unread_mensajes_count(request):
    """Retorna la cantidad de mensajes no leídos para el usuario autenticado."""
    if not request.user.is_authenticated:
        return {"mensajes_no_leidos_total": 0, "unread_mensajes_count": 0}
    try:
        count = LecturaMensaje.objects.filter(
            destinatario=request.user,
            leido=False,
        ).count()
        return {"mensajes_no_leidos_total": count, "unread_mensajes_count": count}
    except Exception:
        return {"mensajes_no_leidos_total": 0, "unread_mensajes_count": 0}
