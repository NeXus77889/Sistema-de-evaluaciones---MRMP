import csv
from uuid import uuid4

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.db.models import Case, IntegerField, Q, When

# pyrefly: ignore[missing-import]
from apps.evaluaciones.academic import (
    LEVELS,
    course_level,
    course_sort_key,
    grouped_course_choices,
)
from apps.usuarios.services import (
    NominaImportError,
    importar_docentes,
    importar_nomina,
    importar_personal,
)

# pyrefly: ignore[missing-import]
from apps.evaluaciones.models import (
    AsignacionDocente,
    Curso,
    EntregaTarea,
    Exam,
    InsumoCalificacion,
    Materia,
    RegistroCalificacion,
    Tarea,
)
from apps.evaluaciones.widgets import GroupedCourseCheckboxSelectMultiple

admin.site.site_header = "Administración Sistema Proctoring — UEPMRMP"
admin.site.site_title = "Sistema Proctoring — UEPMRMP"
admin.site.index_title = "Panel de Control Institucional"


@admin.register(Materia)
class MateriaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo")
    search_fields = ("nombre", "codigo")


@admin.register(Curso)
class CursoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo")
    search_fields = ("nombre", "codigo")
    filter_horizontal = ("estudiantes",)
    change_list_template = "admin/evaluaciones/curso/change_list.html"

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        courses = sorted(queryset, key=course_sort_key)
        ordering = Case(
            *(When(pk=course.pk, then=index) for index, course in enumerate(courses)),
            default=len(courses),
            output_field=IntegerField(),
        )
        return queryset.order_by(ordering)

    def get_urls(self):
        return [
            path(
                "importar-nomina/",
                self.admin_site.admin_view(self.importar_nomina_view),
                name="evaluaciones_curso_importar_nomina",
            ),
            path(
                "importar-docentes/",
                self.admin_site.admin_view(self.importar_docentes_view),
                name="evaluaciones_curso_importar_docentes",
            ),
            path(
                "importar-personal/",
                self.admin_site.admin_view(self.importar_personal_view),
                name="evaluaciones_curso_importar_personal",
            ),
            path(
                "resultado-importacion/<uuid:report_id>/",
                self.admin_site.admin_view(self.resultado_importacion_view),
                name="evaluaciones_curso_resultado_importacion",
            ),
            path(
                "resultado-importacion/<uuid:report_id>/csv/",
                self.admin_site.admin_view(self.descargar_reporte_csv),
                name="evaluaciones_curso_descargar_reporte_csv",
            ),
            *super().get_urls(),
        ]

    def _can_import_students(self, request):
        return all(
            request.user.has_perm(permission)
            for permission in (
                "evaluaciones.add_curso",
                "evaluaciones.change_curso",
                "usuarios.add_user",
                "usuarios.change_user",
            )
        )

    def _can_import_teachers(self, request):
        return all(
            request.user.has_perm(permission)
            for permission in (
                "usuarios.add_user",
                "usuarios.change_user",
                "evaluaciones.view_materia",
                "evaluaciones.view_curso",
                "evaluaciones.add_asignaciondocente",
                "evaluaciones.change_asignaciondocente",
            )
        )

    def _save_report(self, request, summary, title):
        report_id = uuid4()
        request.session[f"credential_import_{report_id}"] = {
            "title": title,
            "rows": summary["reporte"],
        }
        return redirect(
            reverse(
                "admin:evaluaciones_curso_resultado_importacion",
                kwargs={"report_id": report_id},
            )
        )

    def importar_nomina_view(self, request):
        if not self._can_import_students(request):
            raise PermissionDenied

        form = ImportNominaForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            uploaded_file = form.cleaned_data["archivo"]
            try:
                summary = importar_nomina(uploaded_file, uploaded_file.name)
            except NominaImportError as error:
                messages.error(request, str(error))
            else:
                return self._save_report(
                    request,
                    summary,
                    "Resultado de importación de estudiantes",
                )

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Importar nómina de estudiantes",
            "submit_label": "Importar nómina",
            "form": form,
        }
        return render(request, "admin/evaluaciones/curso/import_nomina.html", context)

    def importar_docentes_view(self, request):
        if not self._can_import_teachers(request):
            raise PermissionDenied

        form = ImportDocentesForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            uploaded_file = form.cleaned_data["archivo"]
            try:
                summary = importar_docentes(uploaded_file, uploaded_file.name)
            except NominaImportError as error:
                messages.error(request, str(error))
            else:
                return self._save_report(
                    request,
                    summary,
                    "Resultado de importación de docentes",
                )

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Importar nómina de docentes",
            "submit_label": "Importar docentes",
            "form": form,
        }
        return render(request, "admin/evaluaciones/curso/import_nomina.html", context)

    def importar_personal_view(self, request):
        # Crea cuentas con rol Administrador: solo superusuarios.
        if not request.user.is_superuser:
            raise PermissionDenied

        form = ImportPersonalForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            uploaded_file = form.cleaned_data["archivo"]
            try:
                summary = importar_personal(uploaded_file, uploaded_file.name)
            except NominaImportError as error:
                messages.error(request, str(error))
            else:
                messages.success(
                    request,
                    f"Personal importado: {summary['docentes_creados']} docentes y "
                    f"{summary['administrativos_creados']} administrativos nuevos, "
                    f"{summary['docentes_actualizados'] + summary['administrativos_actualizados']} "
                    f"actualizados, {summary['omitidos']} omitidos (ver reporte).",
                )
                return self._save_report(
                    request,
                    summary,
                    "Resultado de importación de personal",
                )

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Importar personal institucional",
            "submit_label": "Importar personal",
            "form": form,
        }
        return render(request, "admin/evaluaciones/curso/import_nomina.html", context)

    def resultado_importacion_view(self, request, report_id):
        if not (
            self._can_import_students(request)
            or self._can_import_teachers(request)
        ):
            raise PermissionDenied
        report = request.session.get(f"credential_import_{report_id}")
        if report is None:
            raise Http404
        courses = sorted({row["curso"] for row in report["rows"] if row["curso"]})
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": report["title"],
            "report_id": report_id,
            "rows": report["rows"],
            "courses": courses,
        }
        return render(
            request,
            "admin/evaluaciones/curso/resultado_importacion.html",
            context,
        )

    def descargar_reporte_csv(self, request, report_id):
        if not (
            self._can_import_students(request)
            or self._can_import_teachers(request)
        ):
            raise PermissionDenied
        report = request.session.get(f"credential_import_{report_id}")
        if report is None:
            raise Http404

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response.write("\ufeff")
        response["Content-Disposition"] = (
            f'attachment; filename="credenciales_{report_id}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(
            [
                "Nº",
                "Cédula / Usuario",
                "Nombres y Apellidos",
                "Rol",
                "Curso y Paralelo",
                "Clave Temporal",
            ]
        )
        for index, row in enumerate(report["rows"], start=1):
            writer.writerow(
                [
                    index,
                    row["identificacion"],
                    f"{row['nombres']} {row['apellidos']}",
                    row["rol"],
                    row["curso"],
                    row["clave_temporal"],
                ]
            )
        return response


class ImportNominaForm(forms.Form):
    archivo = forms.FileField(label="Archivo Excel")

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        if archivo.name.rsplit(".", 1)[-1].lower() not in {"xlsx", "xls"}:
            raise forms.ValidationError("Selecciona un archivo .xlsx o .xls.")
        if archivo.size > 20 * 1024 * 1024:
            raise forms.ValidationError("El archivo no puede superar 20 MB.")
        return archivo


class ImportDocentesForm(forms.Form):
    archivo = forms.FileField(label="Archivo Excel (.xlsx, .xls) o CSV")

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        if archivo.name.rsplit(".", 1)[-1].lower() not in {"xlsx", "xls", "csv"}:
            raise forms.ValidationError("Selecciona un archivo .xlsx, .xls o .csv.")
        if archivo.size > 20 * 1024 * 1024:
            raise forms.ValidationError("El archivo no puede superar 20 MB.")
        return archivo


class ImportPersonalForm(forms.Form):
    archivo = forms.FileField(
        label="Plantilla de personal (.xlsx, .xls o .csv)",
        help_text=(
            "Columnas: cedula, nombre, correo, funcion_tutoria, asignatura, "
            "curso_paralelo. El rol sale de funcion_tutoria. Las cuentas nuevas "
            "ingresan con su cédula como clave."
        ),
    )

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        if archivo.name.rsplit(".", 1)[-1].lower() not in {"xlsx", "xls", "csv"}:
            raise forms.ValidationError("Selecciona un archivo .xlsx, .xls o .csv.")
        if archivo.size > 20 * 1024 * 1024:
            raise forms.ValidationError("El archivo no puede superar 20 MB.")
        return archivo


class AsignacionDocenteAdminForm(forms.ModelForm):
    cursos = forms.ModelMultipleChoiceField(
        queryset=Curso.objects.all(),
        label="Cursos",
        help_text="Se guardará una asignación normalizada por cada curso seleccionado.",
        widget=GroupedCourseCheckboxSelectMultiple,
    )

    class Meta:
        model = AsignacionDocente
        fields = ("docente", "materia", "activo", "cursos")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cursos"].choices = grouped_course_choices(
            self.fields["cursos"].queryset
        )
        if self.instance.pk:
            self.fields["cursos"].initial = [self.instance.curso_id]

    def clean(self):
        cleaned_data = super().clean()
        courses = list(cleaned_data.get("cursos", ()))
        if not courses:
            self.add_error("cursos", "Selecciona al menos un curso.")
        else:
            self.instance.curso = courses[0]
        return cleaned_data


class EducationalLevelFilter(admin.SimpleListFilter):
    title = "nivel educativo"
    parameter_name = "nivel_educativo"

    def lookups(self, request, model_admin):
        return LEVELS

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        course_ids = [
            course.pk
            for course in Curso.objects.all()
            if course_level(course) == self.value()
        ]
        if queryset.model is Exam:
            return queryset.filter(
                Q(curso_id__in=course_ids) | Q(cursos__pk__in=course_ids)
            ).distinct()
        return queryset.filter(curso_id__in=course_ids)


class ExamCourseFilter(admin.SimpleListFilter):
    title = "curso y paralelo"
    parameter_name = "curso_paralelo"

    def lookups(self, request, model_admin):
        return [
            (course.pk, str(course))
            for course in sorted(Curso.objects.all(), key=course_sort_key)
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(
                Q(curso_id=self.value()) | Q(cursos__pk=self.value())
            ).distinct()
        return queryset


@admin.register(AsignacionDocente)
class AsignacionDocenteAdmin(admin.ModelAdmin):
    form = AsignacionDocenteAdminForm
    list_display = ("docente", "materia", "curso", "activo")
    list_filter = ("activo", "materia", EducationalLevelFilter)
    search_fields = ("docente__username", "docente__first_name", "docente__last_name")

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("curso", "docente", "materia")
        courses = sorted(Curso.objects.all(), key=course_sort_key)
        ordering = Case(
            *(When(curso_id=course.pk, then=index) for index, course in enumerate(courses)),
            default=len(courses),
            output_field=IntegerField(),
        )
        return queryset.order_by(ordering, "materia__nombre", "docente__username")

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        selected_courses = form.cleaned_data.get("cursos", ())
        for course in selected_courses:
            assignment, _ = AsignacionDocente.objects.get_or_create(
                docente=form.instance.docente,
                materia=form.instance.materia,
                curso=course,
                defaults={"activo": form.instance.activo},
            )
            if assignment.activo != form.instance.activo:
                assignment.activo = form.instance.activo
                assignment.save(update_fields=["activo"])


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = (
        "title_display",
        "teacher_display",
        "materia",
        "curso",
        "published_display",
    )
    list_filter = ("published", "materia", EducationalLevelFilter, ExamCourseFilter)
    filter_horizontal = ("cursos", "students")
    search_fields = ("title", "teacher__username")

    @admin.display(description="Evaluación", ordering="title")
    def title_display(self, exam):
        return exam.title

    @admin.display(description="Docente", ordering="teacher__username")
    def teacher_display(self, exam):
        return exam.teacher

    @admin.display(description="Estado", boolean=True, ordering="published")
    def published_display(self, exam):
        return exam.published

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        labels = {
            "title": "Título de la evaluación",
            "description": "Descripción",
            "teacher": "Docente",
            "materia": "Materia",
            "curso": "Curso principal",
            "cursos": "Cursos y paralelos",
            "students": "Estudiantes asignados",
            "duration_minutes": "Duración (minutos)",
            "available_from": "Disponible desde",
            "available_until": "Disponible hasta",
            "published": "Publicada",
            "results_visible": "Mostrar resultados al estudiante",
        }
        if field and db_field.name in labels:
            field.label = labels[db_field.name]
        return field

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "curso" and field is not None:
            field.choices = [
                ("", field.empty_label or "---------"),
                *grouped_course_choices(field.queryset),
            ]
        return field

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        field = super().formfield_for_manytomany(db_field, request, **kwargs)
        if db_field.name == "cursos" and field is not None:
            field.choices = grouped_course_choices(field.queryset)
        return field


@admin.register(Tarea)
class TareaAdmin(admin.ModelAdmin):
    list_display = ("titulo", "curso_display", "materia", "docente", "fecha_entrega", "peso_porcentual", "activo")
    list_filter = ("curso", "materia", "activo")
    search_fields = ("titulo", "descripcion", "docente__username", "docente__first_name", "docente__last_name")

    @admin.display(description="Curso", ordering="curso__nombre")
    def curso_display(self, obj):
        return str(obj.curso)


@admin.register(EntregaTarea)
class EntregaTareaAdmin(admin.ModelAdmin):
    list_display = ("tarea", "estudiante", "estado", "calificacion", "fecha_subida", "fecha_calificacion")
    list_filter = ("estado", "tarea__curso", "tarea__materia")
    search_fields = ("tarea__titulo", "estudiante__username", "estudiante__first_name", "estudiante__last_name")


@admin.register(InsumoCalificacion)
class InsumoCalificacionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "tipo", "periodo", "curso_display", "materia", "docente", "ponderacion", "publicado")
    list_filter = ("tipo", "periodo", "publicado", "curso", "materia")
    search_fields = ("nombre", "docente__username", "docente__first_name", "docente__last_name")

    @admin.display(description="Curso", ordering="curso__nombre")
    def curso_display(self, obj):
        return str(obj.curso)


@admin.register(RegistroCalificacion)
class RegistroCalificacionAdmin(admin.ModelAdmin):
    list_display = ("estudiante", "insumo", "nota", "fecha_registro")
    list_filter = ("insumo__tipo", "insumo__periodo", "insumo__curso")
    search_fields = ("estudiante__username", "estudiante__first_name", "estudiante__last_name", "insumo__nombre")
