from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models, transaction
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
from apps.evaluaciones.grading_config import (
    PESO_ACTIVIDADES_TRIMESTRE,
    PESO_EVALUACION_PARCIAL,
    PESO_EXAMEN_FINAL,
    PESO_INSUMO_1,
    PESO_INSUMO_2,
    PESO_TRIMESTRE_1,
    PESO_TRIMESTRE_2,
    PESO_TRIMESTRE_3,
)
from apps.evaluaciones.models import (
    AsignacionDocente,
    ControlParcial,
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
    if user.rol == "ADMIN":
        messages.warning(
            request,
            "Los administradores supervisan y auditan las tareas; su creación y edición corresponde a los docentes.",
        )
        return redirect("docente-tareas-list")

    tarea = None
    if tarea_id:
        if user.is_superuser:
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

    es_admin = (user.rol == "ADMIN")
    parcial_habilitado = ControlParcial.es_habilitado(tarea.trimestre, tarea.parcial)

    # Procesar calificación individual por POST
    if request.method == "POST" and ("calificar_entrega_id" in request.POST or "calificar_estudiante_id" in request.POST):
        if es_admin:
            messages.error(request, "Los administradores supervisan las tareas pero no pueden calificar entregas.")
            return redirect("docente-tarea-detalle", tarea_id=tarea.pk)

        if not parcial_habilitado:
            messages.error(
                request,
                f"El Trimestre {tarea.trimestre} - Parcial {tarea.parcial} está finalizado o aún no habilitado por la administración. No es posible ingresar calificaciones.",
            )
            return redirect("docente-tarea-detalle", tarea_id=tarea.pk)

        entrega_id = request.POST.get("calificar_entrega_id")
        estudiante_id = request.POST.get("calificar_estudiante_id")
        if entrega_id:
            entrega = get_object_or_404(EntregaTarea, pk=entrega_id, tarea=tarea)
        else:
            estudiante = get_object_or_404(User, pk=estudiante_id, rol=User.Role.STUDENT)
            entrega, _ = EntregaTarea.objects.get_or_create(tarea=tarea, estudiante=estudiante)

        calif_val = request.POST.get("calificacion", "").strip()
        retro = request.POST.get("retroalimentacion", "").strip()

        if calif_val == "":
            entrega.calificacion = None
            entrega.retroalimentacion = retro
            entrega.fecha_calificacion = None
            entrega.save()
            messages.success(request, f"Calificación eliminada para {entrega.estudiante.get_full_name()}.")
        else:
            try:
                val_dec = Decimal(calif_val.replace(",", "."))
                if Decimal("0.00") <= val_dec <= Decimal("10.00"):
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
        "es_admin": es_admin,
        "parcial_habilitado": parcial_habilitado,
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
# DOCENTE: SISTEMA DE CALIFICACIONES INSTITUCIONAL
# ==============================================================================

@login_required
def docente_calificaciones_matrix(request):
    """
    Sábana de calificaciones institucional:
    - 3 Trimestres, cada uno con Primer y Segundo Parcial
    - Examen Final institucional configurable (ej. 20%)
    - Insumo 1 (Tareas / Actividades individuales)
    - Insumo 2 (Lecciones / Proyectos grupales)
    - Evaluación Parcial
    - Guardado por celda en tiempo real (AJAX / fetch) con persistencia y sin pérdida de datos
    - Sincronización automática bidireccional con tareas
    - Publicar calificaciones para estudiantes
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

    try:
        selected_trimestre = int(request.GET.get("trimestre", 1))
    except (ValueError, TypeError):
        selected_trimestre = 1
    if selected_trimestre not in (1, 2, 3):
        selected_trimestre = 1

    try:
        selected_parcial = int(request.GET.get("parcial", 1))
    except (ValueError, TypeError):
        selected_parcial = 1
    if selected_parcial not in (1, 2):
        selected_parcial = 1

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

    es_admin = (user.rol == User.Role.ADMINISTRATOR)
    parcial_habilitado = ControlParcial.es_habilitado(selected_trimestre, selected_parcial)

    # Procesar guardado AJAX / celda individual o guardado masivo
    if request.method == "POST" and selected_curso and selected_materia:
        action = request.POST.get("action", "save_grades")

        # El Administrador solo audita, no califica
        if es_admin:
            if action == "save_single_grade" or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse(
                    {"status": "error", "message": "Los administradores tienen acceso de solo lectura y supervisión en calificaciones."},
                    status=403,
                )
            messages.warning(request, "Los administradores supervisan las calificaciones; los docentes asignados son quienes registran notas.")
            return redirect(
                f"{reverse('docente-calificaciones-matrix')}?curso={selected_curso.pk}&materia={selected_materia.pk}&trimestre={selected_trimestre}&parcial={selected_parcial}"
            )

        # Si el parcial está cerrado / no habilitado por la administración
        if not parcial_habilitado:
            if action == "save_single_grade" or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse(
                    {
                        "status": "error",
                        "message": f"El Trimestre {selected_trimestre} - Parcial {selected_parcial} está finalizado o no habilitado para calificaciones por la administración.",
                    },
                    status=403,
                )
            messages.error(
                request,
                f"El Trimestre {selected_trimestre} - Parcial {selected_parcial} se encuentra finalizado o no habilitado por la administración. No se pueden ingresar ni adelantar calificaciones.",
            )
            return redirect(
                f"{reverse('docente-calificaciones-matrix')}?curso={selected_curso.pk}&materia={selected_materia.pk}&trimestre={selected_trimestre}&parcial={selected_parcial}"
            )

        # Guardado individual por celda (AJAX)
        if action == "save_single_grade" or (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            and "insumo_id" in request.POST
        ):
            insumo_id = request.POST.get("insumo_id")
            estudiante_id = request.POST.get("estudiante_id")
            raw_val = request.POST.get("nota", "").strip()

            insumo = get_object_or_404(
                InsumoCalificacion,
                pk=insumo_id,
                curso=selected_curso,
                materia=selected_materia,
            )
            estudiante = get_object_or_404(User, pk=estudiante_id, rol=User.Role.STUDENT)

            if raw_val == "":
                RegistroCalificacion.objects.filter(
                    insumo=insumo,
                    estudiante=estudiante,
                ).delete()
                nota_guardada = None
            else:
                try:
                    nota_dec = Decimal(raw_val.replace(",", "."))
                    if not (Decimal("0.00") <= nota_dec <= Decimal("10.00")):
                        return JsonResponse(
                            {"status": "error", "message": "La nota debe estar entre 0.00 y 10.00."},
                            status=400,
                        )
                    RegistroCalificacion.objects.update_or_create(
                        insumo=insumo,
                        estudiante=estudiante,
                        defaults={"nota": nota_dec},
                    )
                    nota_guardada = str(nota_dec)
                except (InvalidOperation, ValueError):
                    return JsonResponse(
                        {"status": "error", "message": "Valor de calificación no válido."},
                        status=400,
                    )

            # Recalcular promedio del parcial actual para el estudiante
            insumos_parcial = InsumoCalificacion.objects.filter(
                curso=selected_curso,
                materia=selected_materia,
                trimestre=selected_trimestre,
                parcial=selected_parcial,
            ).exclude(tipo=InsumoCalificacion.TIPO_EXAMEN_FINAL)

            regs = {
                r.insumo_id: r.nota
                for r in RegistroCalificacion.objects.filter(
                    insumo__in=insumos_parcial, estudiante=estudiante
                )
            }
            suma_ponderada = Decimal("0.00")
            suma_pesos = Decimal("0.00")
            for ins in insumos_parcial:
                nota = regs.get(ins.pk)
                if nota is not None:
                    suma_ponderada += nota * ins.ponderacion
                    suma_pesos += ins.ponderacion

            promedio = round(suma_ponderada / suma_pesos, 2) if suma_pesos > 0 else None

            return JsonResponse({
                "status": "ok",
                "message": "Guardado",
                "nota": nota_guardada if nota_guardada is not None else "",
                "promedio": str(promedio) if promedio is not None else "—",
            })

        if action == "publish_all":
            InsumoCalificacion.objects.filter(
                curso=selected_curso,
                materia=selected_materia,
            ).update(publicado=True)
            messages.success(request, "Las calificaciones han sido publicadas oficialmente para los estudiantes.")
            return redirect(
                f"{reverse('docente-calificaciones-matrix')}?curso={selected_curso.pk}&materia={selected_materia.pk}&trimestre={selected_trimestre}&parcial={selected_parcial}"
            )

        elif action == "unpublish_all":
            InsumoCalificacion.objects.filter(
                curso=selected_curso,
                materia=selected_materia,
            ).update(publicado=False)
            messages.info(request, "Las calificaciones se han ocultado (modo borrador).")
            return redirect(
                f"{reverse('docente-calificaciones-matrix')}?curso={selected_curso.pk}&materia={selected_materia.pk}&trimestre={selected_trimestre}&parcial={selected_parcial}"
            )

        elif action == "save_grades":
            # Guardado de la sábana visible
            with transaction.atomic():
                insumos_visibles = InsumoCalificacion.objects.filter(
                    curso=selected_curso,
                    materia=selected_materia,
                ).filter(
                    models.Q(trimestre=selected_trimestre, parcial=selected_parcial)
                    | models.Q(tipo=InsumoCalificacion.TIPO_EXAMEN_FINAL)
                )
                estudiantes = selected_curso.estudiantes.filter(is_active=True)
                for ins in insumos_visibles:
                    for est in estudiantes:
                        key = f"grade_{ins.pk}_{est.pk}"
                        if key in request.POST:
                            raw_val = request.POST.get(key, "").strip()
                            if raw_val:
                                try:
                                    nota_dec = Decimal(raw_val.replace(",", "."))
                                    if Decimal("0.00") <= nota_dec <= Decimal("10.00"):
                                        RegistroCalificacion.objects.update_or_create(
                                            insumo=ins,
                                            estudiante=est,
                                            defaults={"nota": nota_dec},
                                        )
                                except (InvalidOperation, ValueError):
                                    pass
                            else:
                                RegistroCalificacion.objects.filter(
                                    insumo=ins,
                                    estudiante=est,
                                ).delete()

            messages.success(request, "Sábana de calificaciones guardada correctamente.")
            scroll_pos = request.POST.get("scroll_pos", "")
            redirect_url = f"{reverse('docente-calificaciones-matrix')}?curso={selected_curso.pk}&materia={selected_materia.pk}&trimestre={selected_trimestre}&parcial={selected_parcial}"
            if scroll_pos:
                redirect_url += f"&scroll_pos={scroll_pos}"
            return redirect(redirect_url)

        elif action == "create_insumo":
            nombre_ins = request.POST.get("nombre", "").strip()
            tipo_ins = request.POST.get("tipo", InsumoCalificacion.TIPO_INSUMO_1)
            ponderacion_val = request.POST.get("ponderacion", "35.00").strip()
            trim_ins = int(request.POST.get("trimestre", selected_trimestre))
            parc_ins = int(request.POST.get("parcial", selected_parcial))
            asig_first = assignments.filter(curso=selected_curso, materia=selected_materia).first()
            docente_para_insumo = (
                user if user.rol == "DOCENTE"
                else (asig_first.docente if asig_first else (User.objects.filter(rol=User.Role.TEACHER, is_active=True).first() or user))
            )
            try:
                pond_dec = Decimal(ponderacion_val.replace(",", "."))
                InsumoCalificacion.objects.create(
                    curso=selected_curso,
                    materia=selected_materia,
                    docente=docente_para_insumo,
                    nombre=nombre_ins or f"Insumo {tipo_ins}",
                    tipo=tipo_ins,
                    trimestre=trim_ins,
                    parcial=parc_ins,
                    ponderacion=pond_dec,
                    periodo=f"Trimestre {trim_ins} - Parcial {parc_ins}",
                )
                messages.success(request, "Nuevo insumo académico creado.")
            except (InvalidOperation, ValueError) as err:
                messages.error(request, f"Error al crear insumo: {err}")
            return redirect(
                f"{reverse('docente-calificaciones-matrix')}?curso={selected_curso.pk}&materia={selected_materia.pk}&trimestre={selected_trimestre}&parcial={selected_parcial}"
            )

    insumos_parcial = []
    insumo_examen_final = None
    matriz_estudiantes = []
    todos_publicados = False

    if selected_curso and selected_materia:
        # Cargar insumos regulares del trimestre y parcial elegidos
        insumos_parcial = list(
            InsumoCalificacion.objects.filter(
                curso=selected_curso,
                materia=selected_materia,
                trimestre=selected_trimestre,
                parcial=selected_parcial,
            ).exclude(tipo=InsumoCalificacion.TIPO_EXAMEN_FINAL).order_by("tipo", "created_at")
        )

        # Cargar insumo de Examen Final
        insumo_examen_final = InsumoCalificacion.objects.filter(
            curso=selected_curso,
            materia=selected_materia,
            tipo=InsumoCalificacion.TIPO_EXAMEN_FINAL,
        ).first()

        asig_first = assignments.filter(curso=selected_curso, materia=selected_materia).first()
        docente_asignado = (
            user if user.rol == "DOCENTE"
            else (asig_first.docente if asig_first else (User.objects.filter(rol=User.Role.TEACHER, is_active=True).first() or user))
        )

        # Si no existen insumos en este parcial, crear la estructura inicial predeterminada
        if not insumos_parcial:
            with transaction.atomic():
                i1 = InsumoCalificacion.objects.create(
                    curso=selected_curso,
                    materia=selected_materia,
                    docente=docente_asignado,
                    nombre="Insumo 1 (Tareas / Actividades individuales)",
                    tipo=InsumoCalificacion.TIPO_INSUMO_1,
                    trimestre=selected_trimestre,
                    parcial=selected_parcial,
                    periodo=f"Trimestre {selected_trimestre} - Parcial {selected_parcial}",
                    ponderacion=PESO_INSUMO_1,
                )
                i2 = InsumoCalificacion.objects.create(
                    curso=selected_curso,
                    materia=selected_materia,
                    docente=docente_asignado,
                    nombre="Insumo 2 (Lecciones / Proyectos grupales)",
                    tipo=InsumoCalificacion.TIPO_INSUMO_2,
                    trimestre=selected_trimestre,
                    parcial=selected_parcial,
                    periodo=f"Trimestre {selected_trimestre} - Parcial {selected_parcial}",
                    ponderacion=PESO_INSUMO_2,
                )
                ie = InsumoCalificacion.objects.create(
                    curso=selected_curso,
                    materia=selected_materia,
                    docente=docente_asignado,
                    nombre="Evaluación del Parcial",
                    tipo=InsumoCalificacion.TIPO_EVALUACION,
                    trimestre=selected_trimestre,
                    parcial=selected_parcial,
                    periodo=f"Trimestre {selected_trimestre} - Parcial {selected_parcial}",
                    ponderacion=PESO_EVALUACION_PARCIAL,
                )
                insumos_parcial = [i1, i2, ie]

        # Asegurar existencia del Examen Final si no existe
        if not insumo_examen_final:
            insumo_examen_final = InsumoCalificacion.objects.create(
                curso=selected_curso,
                materia=selected_materia,
                docente=docente_asignado,
                nombre="Examen Final Institucional",
                tipo=InsumoCalificacion.TIPO_EXAMEN_FINAL,
                trimestre=3,
                parcial=2,
                periodo="Examen Final",
                ponderacion=PESO_EXAMEN_FINAL,
            )

        todos_insumos = insumos_parcial + ([insumo_examen_final] if insumo_examen_final else [])
        todos_publicados = all(i.publicado for i in todos_insumos) if todos_insumos else False

        registros = RegistroCalificacion.objects.filter(
            insumo__in=todos_insumos
        ).select_related("insumo", "estudiante")
        reg_map = {(r.insumo_id, r.estudiante_id): r.nota for r in registros}

        estudiantes = selected_curso.estudiantes.filter(is_active=True).order_by("last_name", "first_name")

        for est in estudiantes:
            notas_insumos = []
            suma_ponderada = Decimal("0.00")
            suma_pesos = Decimal("0.00")

            for ins in insumos_parcial:
                nota = reg_map.get((ins.pk, est.pk))
                notas_insumos.append({
                    "insumo": ins,
                    "nota": nota,
                })
                if nota is not None:
                    suma_ponderada += nota * ins.ponderacion
                    suma_pesos += ins.ponderacion

            promedio_parcial = round(suma_ponderada / suma_pesos, 2) if suma_pesos > 0 else None
            nota_examen_final = reg_map.get((insumo_examen_final.pk, est.pk)) if insumo_examen_final else None

            matriz_estudiantes.append({
                "estudiante": est,
                "notas_insumos": notas_insumos,
                "promedio": promedio_parcial,
                "nota_examen_final": nota_examen_final,
            })

    return render(request, "docente/calificaciones_matrix.html", {
        "cursos_asignados": cursos_asignados,
        "materias_asignadas": materias_asignadas,
        "selected_curso": selected_curso,
        "selected_materia": selected_materia,
        "selected_trimestre": selected_trimestre,
        "selected_parcial": selected_parcial,
        "insumos": insumos_parcial,
        "insumo_examen_final": insumo_examen_final,
        "matriz_estudiantes": matriz_estudiantes,
        "todos_publicados": todos_publicados,
        "peso_examen_final": PESO_EXAMEN_FINAL,
        "es_admin": es_admin,
        "parcial_habilitado": parcial_habilitado,
    })


# ==============================================================================
# ESTUDIANTE: BOLETÍN DE CALIFICACIONES INSTITUCIONAL
# ==============================================================================

@login_required
def estudiante_calificaciones_boletin(request):
    """
    Portal del Estudiante: Boletín institucional de solo lectura estructurado por:
    - 3 Trimestres, cada uno con Primer y Segundo Parcial
    - Examen Final Institucional
    - Promedio Anual ponderado
    Solo muestra calificaciones explícitamente publicadas por el docente.
    """
    if not _is_estudiante(request.user):
        raise PermissionDenied("Acceso exclusivo para estudiantes.")

    user = request.user
    cursos = user.cursos.all()

    materias_boletin = []

    for curso in cursos:
        materias_curso = Materia.objects.filter(
            asignaciones__curso=curso,
            asignaciones__activo=True,
        ).distinct()

        for mat in materias_curso:
            insumos = list(
                InsumoCalificacion.objects.filter(
                    curso=curso,
                    materia=mat,
                    publicado=True,
                ).order_by("trimestre", "parcial", "tipo", "created_at")
            )

            if not insumos:
                continue

            registros = {
                r.insumo_id: r.nota
                for r in RegistroCalificacion.objects.filter(
                    insumo__in=insumos, estudiante=user
                )
            }

            trimestres_data = []
            promedios_trimestres = []

            for t_num in (1, 2, 3):
                parciales_data = []
                promedios_parciales = []

                for p_num in (1, 2):
                    insumos_p = [
                        i for i in insumos
                        if i.trimestre == t_num and i.parcial == p_num and i.tipo != InsumoCalificacion.TIPO_EXAMEN_FINAL
                    ]
                    insumos_p_detalle = []
                    suma_p = Decimal("0.00")
                    pesos_p = Decimal("0.00")

                    for ins in insumos_p:
                        nota = registros.get(ins.pk)
                        insumos_p_detalle.append({
                            "nombre": ins.nombre,
                            "tipo": ins.get_tipo_display(),
                            "ponderacion": ins.ponderacion,
                            "nota": nota,
                        })
                        if nota is not None:
                            suma_p += nota * ins.ponderacion
                            pesos_p += ins.ponderacion

                    prom_p = round(suma_p / pesos_p, 2) if pesos_p > 0 else None
                    if prom_p is not None:
                        promedios_parciales.append(prom_p)

                    parciales_data.append({
                        "numero": p_num,
                        "nombre": f"Parcial {p_num}",
                        "insumos": insumos_p_detalle,
                        "promedio": prom_p,
                    })

                prom_t = (
                    round(sum(promedios_parciales) / len(promedios_parciales), 2)
                    if promedios_parciales else None
                )
                if prom_t is not None:
                    promedios_trimestres.append((t_num, prom_t))

                trimestres_data.append({
                    "numero": t_num,
                    "nombre": f"Trimestre {t_num}",
                    "parciales": parciales_data,
                    "promedio": prom_t,
                })

            # Examen final publicado
            insumo_final = next(
                (i for i in insumos if i.tipo == InsumoCalificacion.TIPO_EXAMEN_FINAL),
                None,
            )
            nota_examen_final = registros.get(insumo_final.pk) if insumo_final else None

            # Cálculo de promedio anual
            promedio_anual = None
            if promedios_trimestres:
                peso_map = {1: PESO_TRIMESTRE_1, 2: PESO_TRIMESTRE_2, 3: PESO_TRIMESTRE_3}
                suma_trimestral = sum(prom * peso_map[t] for t, prom in promedios_trimestres)
                pesos_trimestres = sum(peso_map[t] for t, _ in promedios_trimestres)
                if pesos_trimestres > 0:
                    prom_trimestres_base = suma_trimestral / pesos_trimestres
                    if nota_examen_final is not None:
                        promedio_anual = round(
                            (prom_trimestres_base * (PESO_ACTIVIDADES_TRIMESTRE / 100))
                            + (nota_examen_final * (PESO_EXAMEN_FINAL / 100)),
                            2,
                        )
                    else:
                        promedio_anual = round(prom_trimestres_base, 2)

            estado_cualitativo = ""
            if promedio_anual is not None:
                if promedio_anual >= Decimal("9.00"):
                    estado_cualitativo = "Domina los aprendizajes (DAR)"
                elif promedio_anual >= Decimal("7.00"):
                    estado_cualitativo = "Alcanza los aprendizajes (AAR)"
                elif promedio_anual >= Decimal("4.01"):
                    estado_cualitativo = "Próximo a alcanzar (PAAR)"
                else:
                    estado_cualitativo = "No alcanza los aprendizajes (NAAR)"

            materias_boletin.append({
                "curso": curso,
                "materia": mat,
                "trimestres": trimestres_data,
                "nota_examen_final": nota_examen_final,
                "promedio_anual": promedio_anual,
                "estado_cualitativo": estado_cualitativo,
            })

    return render(request, "estudiante/calificaciones_boletin.html", {
        "materias_boletin": materias_boletin,
        "cursos": cursos,
        "fecha_actual": timezone.now(),
        "peso_examen_final": PESO_EXAMEN_FINAL,
    })

