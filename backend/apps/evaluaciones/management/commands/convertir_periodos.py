import re
from django.core.management.base import BaseCommand
from apps.evaluaciones.models import InsumoCalificacion, Tarea


class Command(BaseCommand):
    help = (
        "Lee el texto antiguo de 'periodo' ('Primer Quimestre - Parcial 1', etc.) "
        "y rellena los campos 'trimestre' y 'parcial' en InsumoCalificacion y Tarea."
    )

    def handle(self, *args, **options):
        self.stdout.write("Iniciando conversión de periodos a trimestres y parciales...")
        insumos = InsumoCalificacion.objects.all()
        actualizados = 0

        for insumo in insumos:
            texto = (insumo.periodo or "").lower()
            nombre = (insumo.nombre or "").lower()

            trimestre = 1
            parcial = 1

            # Detección de Examen Final
            if "examen final" in texto or "examen final" in nombre:
                if insumo.tipo != InsumoCalificacion.TIPO_EXAMEN_FINAL:
                    insumo.tipo = InsumoCalificacion.TIPO_EXAMEN_FINAL

            # Detección de Trimestre / Quimestre
            if any(term in texto for term in ["tercer trimestre", "trimestre 3", "3er trimestre", "3º trimestre"]):
                trimestre = 3
            elif any(term in texto for term in ["segundo quimestre", "segundo trimestre", "quimestre 2", "trimestre 2", "2do quimestre", "2do trimestre"]):
                trimestre = 2
            else:
                trimestre = 1

            # Detección de Parcial
            if any(term in texto for term in ["parcial 2", "segundo parcial", "p2", "2do parcial", "parcial ii"]):
                parcial = 2
            else:
                parcial = 1

            # Si el insumo está vinculado a una Tarea, verificar si la tarea tiene valores definidos
            if insumo.tarea_id:
                trimestre = insumo.tarea.trimestre or trimestre
                parcial = insumo.tarea.parcial or parcial

            cambio = False
            if insumo.trimestre != trimestre:
                insumo.trimestre = trimestre
                cambio = True
            if insumo.parcial != parcial:
                insumo.parcial = parcial
                cambio = True

            if cambio:
                insumo.save(update_fields=["trimestre", "parcial", "tipo"])
                actualizados += 1

        # También sincronizar tareas existentes con su insumo
        tareas_actualizadas = 0
        for tarea in Tarea.objects.all():
            insumo = tarea.asegurar_insumo()
            if insumo:
                if tarea.trimestre != insumo.trimestre or tarea.parcial != insumo.parcial:
                    tarea.trimestre = insumo.trimestre
                    tarea.parcial = insumo.parcial
                    tarea.save(update_fields=["trimestre", "parcial"])
                    tareas_actualizadas += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Conversión completada con éxito. "
                f"{actualizados} insumo(s) actualizados, {tareas_actualizadas} tarea(s) sincronizadas."
            )
        )

