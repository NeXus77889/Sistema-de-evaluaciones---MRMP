from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.evaluaciones.academic import course_sort_key, format_course_name
from apps.evaluaciones.forms import (
    CalificarEntregaForm,
    EntregaTareaForm,
    InsumoCalificacionForm,
    TareaForm,
)
from apps.evaluaciones.models import (
    AsignacionDocente,
    Curso,
    EntregaTarea,
    InsumoCalificacion,
    Materia,
    RegistroCalificacion,
    Tarea,
)
from apps.usuarios.models import User


def _is_docente(user):
    return user.is_authenticated and (user.rol == "DOCENTE" or user.is_superuser or user.rol == "ADMIN")


def _is_estudiante(user):
    return user.is_authenticated and user.rol == "ESTUDIANTE"


# ==============================================================================
# DOCENTE: MÓDULO DE TAREAS Y ENTREGAS
# ==============================================================================

@login_required
def docente_tareas_list(request):
    if not _is_docente(request.user):
        raise PermissionDenied("Acceso restringido para docentes.")

    user = request.user
    if user.is_superuser or user.rol == "ADMIN":
        tareas = Tarea.objects.all().select_related("curso", "materia", "docente")
    else:
        tareas = Tarea.objects.filter(docente=user).select_related("curso", "materia", "docente")

    # Filtros
    curso_id = request.GET.get("curso")
    materia_id = request.GET.get("materia")
    if curso_id:
        tareas = tareas.filter(curso_id=curso_id)
    if materia_id:
        tareas = tareas.filter(materia_id=materia_id)

    # Añadir estadísticas de entrega a cada tarea
    tareas_data = []
    for t in tareas:
        total_alumnos = t.curso.estudiantes.filter(is_active=True).count()
        entregas_qs = t.entregas.all()
        entregados = entregas_qs.filter(estado__in=[EntregaTarea.ESTADO_ENTREGADO, EntregaTarea.ESTADO_ATRASADO]).count()
        calificados = entregas_qs.filter(calificacion__isnull=False).count()
        pendientes = max(0, total_alumnos - entregados)
        tareas_data.append({
            "tarea": t,
            "total_alumnos": total_alumnos,
            "entregados": entregados,
            "pendientes": pendientes,
            "calificados": calificados,
        })

    # Cursos y materias asignados para filtro
    if user.is_superuser or user.rol == "ADMIN":
        cursos_filtro = sorted(Curso.objects.all(), key=course_sort_key)
        materias_filtro = Materia.objects.all()
    else:
        assignments = AsignacionDocente.objects.filter(docente=user, activo=True)
        cursos_filtro = sorted(Curso.objects.filter(asignaciones__in=assignments).distinct(), key=course_sort_key)
        materias_filtro = Materia.objects.filter(asignaciones__in=assignments).distinct()

    return render(request, "docente/tareas_list.html", {
        "tareas_data": tareas_data,
        "cursos_filtro": cursos_filtro,
        "materias_filtro": materias_filtro,
        "selected_curso": curso_id,
        "selected_materia": materia_id,
    })


@login_required
def docente_tarea_form(request, tarea_id=None):
    if not _is_docente(request.user):
        raise PermissionDenied("Acceso restringido para docentes.")

    user = request.user
    tarea = None
    if tarea_id:
        if user.is_superuser or user.rol == "ADMIN":
            tarea = get_object_or_404(Tarea, pk=tarea_id)
        else:
            tarea = get_object_or_404(Tarea, pk=tarea_id, docente=user)

    if request.method == "POST":
        form = TareaForm(request.POST, request.FILES, instance=tarea, docente=user)
        if form.is_valid():
            tarea_obj = form.save(commit=False)
            if not tarea_obj.docente_id:
                tarea_obj.docente = user
            tarea_obj.save()
            messages.success(request, f"Tarea '{tarea_obj.titulo}' guardada exitosamente.")
            return redirect("docente-tareas-list")
    else:
        form = TareaForm(instance=tarea, docente=user)

    return render(request, "docente/tarea_form.html", {
        "form": form,
        "tarea": tarea,
        "is_edit": bool(tarea_id),
    })


@login_required
def docente_tarea_detalle(request, tarea_id):
    """
    Panel interactivo con matriz de control (verde para entregado, rojo/gris para pendiente,
    amarillo para atrasado) y gestión de calificaciones de entregas.
    """
    if not _is_docente(request.user):
        raise PermissionDenied("Acceso restringido para docentes.")

    user = request.user
    if user.is_superuser or user.rol == "ADMIN":
        tarea = get_object_or_404(Tarea.objects.select_related("curso", "materia", "docente"), pk=tarea_id)
    else:
        tarea = get_object_or_404(Tarea.objects.select_related("curso", "materia", "docente"), pk=tarea_id, docente=user)

    # Procesar calificación individual por POST
    if request.method == "POST" and "calificar_entrega_id" in request.POST:
        entrega_id = request.POST.get("calificar_entrega_id")
        entrega = get_object_or_404(EntregaTarea, pk=entrega_id, tarea=tarea)
        calif_val = request.POST.get("calificacion", "").strip()
        retro = request.POST.get("retroalimentacion", "").strip()
        try:
            val_dec = Decimal(calif_val.replace(",", "."))
            if 0.00 <= val_dec <= 10.00:
                entrega.calificacion = val_dec
                entrega.retroalimentacion = retro
                entrega.fecha_calificacion = timezone.now()
                entrega.save()
                messages.success(request, f"Calificación guardada para {entrega.estudiante.get_full_name()}.")
            else:
                messages.error(request, "La calificación debe estar entre 0.00 y 10.00.")
        except (InvalidOperation, ValueError):
            messages.error(request, "Valor de calificación no válido.")
        return redirect("docente-tarea-detalle", tarea_id=tarea.pk)

    # Construir Matriz de Control de Estudiantes del Curso
    estudiantes = tarea.curso.estudiantes.filter(is_active=True).order_by("last_name", "first_name")
    entregas_map = {e.estudiante_id: e for e in tarea.entregas.select_related("estudiante")}

    matriz = []
    conteo_entregados = 0
    conteo_atrasados = 0
    conteo_pendientes = 0
    conteo_calificados = 0

    for est in estudiantes:
        entrega = entregas_map.get(est.pk)
        if entrega:
            if entrega.calificacion is not None:
                conteo_calificados += 1
            if entrega.estado == EntregaTarea.ESTADO_ATRASADO:
                conteo_atrasados += 1
            else:
                conteo_entregados += 1
        else:
            conteo_pendientes += 1

        matriz.append({
            "estudiante": est,
            "entrega": entrega,
            "estado": entrega.estado if entrega else "PENDIENTE",
            "tiene_archivo": bool(entrega and entrega.archivo),
            "calificacion": entrega.calificacion if entrega else None,
            "retroalimentacion": entrega.retroalimentacion if entrega else "",
        })

    return render(request, "docente/tarea_detalle.html", {
        "tarea": tarea,
        "matriz": matriz,
        "total_estudiantes": len(estudiantes),
        "conteo_entregados": conteo_entregados,
        "conteo_atrasados": conteo_atrasados,
        "conteo_pendientes": conteo_pendientes,
        "conteo_calificados": conteo_calificados,
    })


# ==============================================================================
# ESTUDIANTE: MÓDULO DE TAREAS Y SUBIDA DE ENTREGAS
# ==============================================================================

@login_required
def estudiante_tareas_list(request):
    if not _is_estudiante(request.user):
        raise PermissionDenied("Acceso exclusivo para estudiantes.")

    user = request.user
    cursos_alumno = user.cursos.all()
    tareas = (
        Tarea.objects.filter(curso__in=cursos_alumno, activo=True)
        .select_related("curso", "materia", "docente")
        .order_by("fecha_entrega")
    )

    entregas_map = {e.tarea_id: e for e in EntregaTarea.objects.filter(estudiante=user)}

    tareas_data = []
    for t in tareas:
        entrega = entregas_map.get(t.pk)
        now = timezone.now()
        is_vencida = bool(t.fecha_entrega and now > t.fecha_entrega)
        tareas_data.append({
            "tarea": t,
            "entrega": entrega,
            "estado": entrega.estado if entrega else ("ATRASADO" if is_vencida else "PENDIENTE"),
            "is_vencida": is_vencida,
        })

    return render(request, "estudiante/tareas_list.html", {
        "tareas_data": tareas_data,
    })


@login_required
def estudiante_tarea_entrega(request, tarea_id):
    if not _is_estudiante(request.user):
        raise PermissionDenied("Acceso exclusivo para estudiantes.")

    user = request.user
    tarea = get_object_or_404(
        Tarea.objects.select_related("curso", "materia", "docente"),
        pk=tarea_id,
        curso__in=user.cursos.all(),
        activo=True,
    )

    entrega, _ = EntregaTarea.objects.get_or_create(
        tarea=tarea,
        estudiante=user,
    )

    if request.method == "POST":
        form = EntregaTareaForm(request.POST, request.FILES, instance=entrega)
        if form.is_valid():
            entrega_obj = form.save(commit=False)
            now = timezone.now()
            if tarea.fecha_entrega and now > tarea.fecha_entrega:
                entrega_obj.estado = EntregaTarea.ESTADO_ATRASADO
            else:
                entrega_obj.estado = EntregaTarea.ESTADO_ENTREGADO
            entrega_obj.save()
            messages.success(request, "Tu tarea ha sido entregada correctamente.")
            return redirect("estudiante-tareas-list")
    else:
        form = EntregaTareaForm(instance=entrega)

    return render(request, "estudiante/tarea_entrega.html", {
        "tarea": tarea,
        "entrega": entrega,
        "form": form,
    })


# ==============================================================================
# DOCENTE: SISTEMA DE CALIFICACIONES INSTITUCIONAL (ESTILO RUNACHAY)
# ==============================================================================

@login_required
def docente_calificaciones_matrix(request):
    """
    Sábana de calificaciones institucional (Estilo Runachay):
    - Insumo 1 (Tareas / Actividades)
    - Insumo 2 (Lecciones / Proyectos)
    - Evaluación Parcial
    - Promedio Ponderado en tiempo real
    - Carga masiva de notas
    - Publicar Calificaciones para los alumnos
    """
    if not _is_docente(request.user):
        raise PermissionDenied("Acceso restringido para docentes.")

    user = request.user
    if user.is_superuser or user.rol == "ADMIN":
        assignments = AsignacionDocente.objects.filter(activo=True)
    else:
        assignments = AsignacionDocente.objects.filter(docente=user, activo=True)

    cursos_asignados = sorted(Curso.objects.filter(asignaciones__in=assignments).distinct(), key=course_sort_key)
    curso_id = request.GET.get("curso")
    materia_id = request.GET.get("materia")

    selected_curso = None
    selected_materia = None
    materias_asignadas = []

    if curso_id:
        try:
            selected_curso = Curso.objects.get(pk=curso_id)
            materias_asignadas = Materia.objects.filter(
                asignaciones__in=assignments.filter(curso=selected_curso)
            ).distinct()
        except Curso.DoesNotExist:
            selected_curso = None

    if selected_curso and materia_id:
        try:
            selected_materia = Materia.objects.get(pk=materia_id)
            if not (user.is_superuser or user.rol == "ADMIN"):
                # Strict RBAC verification
                has_access = AsignacionDocente.objects.filter(
                    docente=user,
                    curso=selected_curso,
                    materia=selected_materia,
                    activo=True,
                ).exists()
                if not has_access:
                    raise PermissionDenied("No tienes asignada esta materia en este curso.")
        except Materia.DoesNotExist:
            selected_materia = None

    # Procesar guardado masivo de notas o publicación
    if request.method == "POST" and selected_curso and selected_materia:
        action = request.POST.get("action", "save_grades")

        if action == "publish_all":
            # Publicar todos los insumos de esta materia y curso
            InsumoCalificacion.objects.filter(
                curso=selected_curso,
                materia=selected_materia,
            ).update(publicado=True)
            messages.success(request, "Las calificaciones han sido publicadas oficialmente para los estudiantes.")
            return redirect(f"{reverse('docente-calificaciones-matrix')}?curso={selected_curso.pk}&materia={selected_materia.pk}")

        elif action == "unpublish_all":
            InsumoCalificacion.objects.filter(
                curso=selected_curso,
                materia=selected_materia,
            ).update(publicado=False)
            messages.info(request, "Las calificaciones se han ocultado (modo borrador).")
            return redirect(f"{reverse('docente-calificaciones-matrix')}?curso={selected_curso.pk}&materia={selected_materia.pk}")

        elif action == "save_grades":
            # Guardado masivo de matriz
            with transaction.atomic():
                insumos = InsumoCalificacion.objects.filter(
                    curso=selected_curso,
                    materia=selected_materia,
                )
                estudiantes = selected_curso.estudiantes.filter(is_active=True)
                for ins in insumos:
                    for est in estudiantes:
                        key = f"grade_{ins.pk}_{est.pk}"
                        if key in request.POST:
                            raw_val = request.POST.get(key, "").strip()
                            if raw_val:
                                try:
                                    nota_dec = Decimal(raw_val.replace(",", "."))
                                    if 0.00 <= nota_dec <= 10.00:
                                        RegistroCalificacion.objects.update_or_create(
                                            insumo=ins,
                                            estudiante=est,
                                            defaults={"nota": nota_dec},
                                        )
                                except (InvalidOperation, ValueError):
                                    pass
                            else:
                                # Si se deja en blanco, eliminar registro si existía
                                RegistroCalificacion.objects.filter(insumo=ins, estudiante=est).delete()

            messages.success(request, "Sábana de calificaciones guardada correctamente.")
            return redirect(f"{reverse('docente-calificaciones-matrix')}?curso={selected_curso.pk}&materia={selected_materia.pk}")

        elif action == "create_insumo":
            nombre_ins = request.POST.get("nombre", "").strip()
            tipo_ins = request.POST.get("tipo", InsumoCalificacion.TIPO_INSUMO_1)
            ponderacion_val = request.POST.get("ponderacion", "35.00").strip()
            periodo_val = request.POST.get("periodo", "Primer Quimestre - Parcial 1").strip()
            try:
                pond_dec = Decimal(ponderacion_val.replace(",", "."))
                InsumoCalificacion.objects.create(
                    curso=selected_curso,
                    materia=selected_materia,
                    docente=user,
                    nombre=nombre_ins or f"Insumo {tipo_ins}",
                    tipo=tipo_ins,
                    ponderacion=pond_dec,
                    periodo=periodo_val,
                )
                messages.success(request, "Nuevo insumo académico creado.")
            except (InvalidOperation, ValueError) as err:
                messages.error(request, f"Error al crear insumo: {err}")
            return redirect(f"{reverse('docente-calificaciones-matrix')}?curso={selected_curso.pk}&materia={selected_materia.pk}")

    # Si hay curso y materia seleccionados, cargar o inicializar insumos por defecto (Runachay)
    insumos = []
    matriz_estudiantes = []
    todos_publicados = False

    if selected_curso and selected_materia:
        insumos = list(
            InsumoCalificacion.objects.filter(
                curso=selected_curso,
                materia=selected_materia,
            ).order_by("tipo", "created_at")
        )

        # Si no existen insumos aún, inicializar la estructura institucional Runachay:
        # Insumo 1 (35%), Insumo 2 (35%), Evaluación (30%)
        if not insumos:
            with transaction.atomic():
                i1 = InsumoCalificacion.objects.create(
                    curso=selected_curso,
                    materia=selected_materia,
                    docente=user if user.rol == "DOCENTE" else assignments.filter(curso=selected_curso, materia=selected_materia).first().docente,
                    nombre="Insumo 1 (Tareas / Actividades individuales)",
                    tipo=InsumoCalificacion.TIPO_INSUMO_1,
                    ponderacion=Decimal("35.00"),
                    periodo="Primer Quimestre - Parcial 1",
                )
                i2 = InsumoCalificacion.objects.create(
                    curso=selected_curso,
                    materia=selected_materia,
                    docente=user if user.rol == "DOCENTE" else assignments.filter(curso=selected_curso, materia=selected_materia).first().docente,
                    nombre="Insumo 2 (Lecciones / Proyectos grupales)",
                    tipo=InsumoCalificacion.TIPO_INSUMO_2,
                    ponderacion=Decimal("35.00"),
                    periodo="Primer Quimestre - Parcial 1",
                )
                ie = InsumoCalificacion.objects.create(
                    curso=selected_curso,
                    materia=selected_materia,
                    docente=user if user.rol == "DOCENTE" else assignments.filter(curso=selected_curso, materia=selected_materia).first().docente,
                    nombre="Evaluación del Parcial",
                    tipo=InsumoCalificacion.TIPO_EVALUACION,
                    ponderacion=Decimal("30.00"),
                    periodo="Primer Quimestre - Parcial 1",
                )
                insumos = [i1, i2, ie]

        todos_publicados = all(i.publicado for i in insumos) if insumos else False

        # Cargar todos los registros existentes para este conjunto de insumos
        registros = RegistroCalificacion.objects.filter(insumo__in=insumos).select_related("insumo", "estudiante")
        reg_map = {(r.insumo_id, r.estudiante_id): r.nota for r in registros}

        estudiantes = selected_curso.estudiantes.filter(is_active=True).order_by("last_name", "first_name")

        for est in estudiantes:
            notas_insumos = []
            suma_ponderada = Decimal("0.00")
            suma_pesos = Decimal("0.00")

            for ins in insumos:
                nota = reg_map.get((ins.pk, est.pk))
                notas_insumos.append({
                    "insumo": ins,
                    "nota": nota,
                })
                if nota is not None:
                    suma_ponderada += nota * ins.ponderacion
                    suma_pesos += ins.ponderacion

            if suma_pesos > 0:
                promedio_ponderado = round(suma_ponderada / suma_pesos, 2)
            else:
                promedio_ponderado = None

            matriz_estudiantes.append({
                "estudiante": est,
                "notas_insumos": notas_insumos,
                "promedio": promedio_ponderado,
            })

    return render(request, "docente/calificaciones_matrix.html", {
        "cursos_asignados": cursos_asignados,
        "materias_asignadas": materias_asignadas,
        "selected_curso": selected_curso,
        "selected_materia": selected_materia,
        "insumos": insumos,
        "matriz_estudiantes": matriz_estudiantes,
        "todos_publicados": todos_publicados,
    })


# ==============================================================================
# ESTUDIANTE: BOLETÍN DE CALIFICACIONES INSTITUCIONAL (ESTILO RUNACHAY)
# ==============================================================================

@login_required
def estudiante_calificaciones_boletin(request):
    """
    Portal del Estudiante: Boletín institucional de solo lectura con detalle de
    calificaciones por materia, organizadas por Insumos y Evaluación Parcial (Runachay).
    Solo muestra calificaciones explícitamente publicadas por el docente.
    """
    if not _is_estudiante(request.user):
        raise PermissionDenied("Acceso exclusivo para estudiantes.")

    user = request.user
    cursos = user.cursos.all()

    # Obtener todas las materias asociadas a los cursos del estudiante
    materias_boletin = []

    for curso in cursos:
        # Materias asignadas activamente a este curso
        materias_curso = Materia.objects.filter(asignaciones__curso=curso, asignaciones__activo=True).distinct()
        for mat in materias_curso:
            # Buscar insumos publicados para este curso y materia
            insumos = list(
                InsumoCalificacion.objects.filter(
                    curso=curso,
                    materia=mat,
                    publicado=True,
                ).order_by("tipo", "created_at")
            )

            if not insumos:
                continue

            registros = {
                r.insumo_id: r.nota
                for r in RegistroCalificacion.objects.filter(insumo__in=insumos, estudiante=user)
            }

            insumos_detalle = []
            suma_ponderada = Decimal("0.00")
            suma_pesos = Decimal("0.00")

            for ins in insumos:
                nota = registros.get(ins.pk)
                insumos_detalle.append({
                    "nombre": ins.nombre,
                    "tipo": ins.get_tipo_display(),
                    "ponderacion": ins.ponderacion,
                    "nota": nota,
                })
                if nota is not None:
                    suma_ponderada += nota * ins.ponderacion
                    suma_pesos += ins.ponderacion

            promedio = round(suma_ponderada / suma_pesos, 2) if suma_pesos > 0 else None

            # Estado cualitativo según escala ministerial (Runachay)
            estado_cualitativo = ""
            if promedio is not None:
                if promedio >= Decimal("9.00"):
                    estado_cualitativo = "Domina los aprendizajes (DAR)"
                elif promedio >= Decimal("7.00"):
                    estado_cualitativo = "Alcanza los aprendizajes (AAR)"
                elif promedio >= Decimal("4.01"):
                    estado_cualitativo = "Próximo a alcanzar (PAAR)"
                else:
                    estado_cualitativo = "No alcanza los aprendizajes (NAAR)"

            materias_boletin.append({
                "curso": curso,
                "materia": mat,
                "insumos": insumos_detalle,
                "promedio": promedio,
                "estado_cualitativo": estado_cualitativo,
            })

    return render(request, "estudiante/calificaciones_boletin.html", {
        "materias_boletin": materias_boletin,
        "cursos": cursos,
        "fecha_actual": timezone.now(),
    })

