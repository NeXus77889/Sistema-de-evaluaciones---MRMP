"""Detección de IPs cercanas entre estudiantes de una misma evaluación.

Dos intentos se consideran cercanos si comparten la misma IP o si sus IP caen
en la misma red (por defecto /24 en IPv4 y /64 en IPv6). Es solo un indicador
para revisión del docente: varios estudiantes pueden compartir red de forma
legítima (misma casa, mismo Wi-Fi, red móvil con CGNAT).
"""

import ipaddress
from dataclasses import dataclass

from django.conf import settings

from apps.intentos.models import Attempt


def get_client_ip(request):
    """Devuelve la IP del cliente o None si no se puede determinar.

    Detrás de proxies (Render, Cloudflare) REMOTE_ADDR es la IP del proxy. Se usa
    X-Forwarded-For contando desde la derecha CLIENT_IP_PROXY_HOPS entradas, porque
    las entradas de la izquierda las puede inventar el propio estudiante.
    """
    hops = max(1, int(getattr(settings, "CLIENT_IP_PROXY_HOPS", 3)))
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    parts = [part.strip() for part in forwarded.split(",") if part.strip()]
    candidate = ""
    if parts:
        candidate = parts[-hops] if len(parts) >= hops else parts[0]
    if not candidate:
        candidate = request.META.get("REMOTE_ADDR", "")
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def network_of(ip):
    """Red a la que pertenece una IP, según el prefijo configurado."""
    address = ipaddress.ip_address(ip)
    if address.version == 4:
        prefix = int(getattr(settings, "NEARBY_IP_IPV4_PREFIX", 24))
    else:
        prefix = int(getattr(settings, "NEARBY_IP_IPV6_PREFIX", 64))
    return ipaddress.ip_network(f"{address}/{prefix}", strict=False)


@dataclass(frozen=True)
class NearbyAttempt:
    attempt: Attempt
    relation: str  # "Misma IP" o "Misma red"


def find_nearby_attempts(attempt):
    """Otros intentos de la misma evaluación con IP igual o de la misma red."""
    if not attempt.ip_address:
        return []
    own_ip = ipaddress.ip_address(attempt.ip_address)
    own_network = network_of(attempt.ip_address)
    others = (
        Attempt.objects.filter(exam_id=attempt.exam_id)
        .exclude(pk=attempt.pk)
        .exclude(ip_address__isnull=True)
        .select_related("student")
        .order_by("student__last_name", "student__first_name", "pk")
    )
    nearby = []
    for other in others:
        other_ip = ipaddress.ip_address(other.ip_address)
        if other_ip == own_ip:
            nearby.append(NearbyAttempt(other, "Misma IP"))
        elif other_ip.version == own_ip.version and other_ip in own_network:
            nearby.append(NearbyAttempt(other, "Misma red"))
    return nearby
