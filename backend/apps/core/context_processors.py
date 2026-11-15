from datetime import timedelta
from django.utils import timezone
from apps.evaluaciones.models import Exam
from apps.usuarios.models import User


def evaluaciones_admin_context(request):
    """Retorna el contador de evaluaciones pendientes de aprobación para el administrador."""
    if not request.user.is_authenticated or request.user.rol != User.Role.ADMINISTRATOR:
        return {"total_exams_nuevas": 0, "total_exams_pendientes": 0}
    try:
        umbral_nueva = timezone.now() - timedelta(days=7)
        total_nuevas = Exam.objects.filter(created_at__gte=umbral_nueva).count()
        total_pendientes = Exam.objects.filter(aprobada=False).count()
        return {
            "total_exams_nuevas": total_nuevas,
            "total_exams_pendientes": total_pendientes,
        }
    except Exception:
        return {"total_exams_nuevas": 0, "total_exams_pendientes": 0}

