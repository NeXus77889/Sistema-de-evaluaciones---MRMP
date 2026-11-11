from django import forms
from django.contrib.auth import get_user_model

# pyrefly: ignore[missing-import]
from apps.evaluaciones.academic import grouped_course_choices
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

# pyrefly: ignore[missing-import]
from apps.usuarios.models import User

User = get_user_model()


class ExamForm(forms.ModelForm):
    cursos = forms.ModelMultipleChoiceField(
        queryset=Curso.objects.all(),
        required=False,
        label="Cursos destino",
        help_text="Selecciona uno o varios cursos; el examen estará disponible en todos.",
        widget=GroupedCourseCheckboxSelectMultiple,
    )

    def __init__(self, *args, docente=None, **kwargs):
        docente = kwargs.pop("docente", docente)
        super().__init__(*args, **kwargs)
        self.docente = docente
        self.assignment_notice = ""
        self.fields["curso"].required = False
        self.fields["curso"].widget = forms.HiddenInput()

        student_role = getattr(User.Role, "STUDENT", "ESTUDIANTE") if hasattr(User, "Role") else "ESTUDIANTE"
        self.fields["students"].queryset = User.objects.filter(
            rol=student_role, is_active=True
        )
        self.fields["duration_minutes"].widget.attrs["min"] = 1

        is_administrator = docente and (
            docente.is_superuser or docente.rol == User.Role.ADMINISTRATOR
        )
        if is_administrator:
            self.fields["materia"].queryset = Materia.objects.all()
            self.fields["curso"].queryset = Curso.objects.all()
        elif docente is not None:
            self.instance.teacher = docente
            assignments = AsignacionDocente.objects.filter(docente=docente, activo=True)
            assigned_courses = Curso.objects.filter(asignaciones__in=assignments).distinct()
            self.fields["materia"].queryset = Materia.objects.filter(
                asignaciones__in=assignments
            ).distinct()
            self.fields["curso"].queryset = assigned_courses
            self.fields["cursos"].queryset = assigned_courses
            if not assignments.exists():
                self.assignment_notice = (
                    "No tienes asignaciones activas. Solicita a Secretaría "
                    "la asignación de materias y cursos."
                )

            if self.is_bound:
                selected_course = self.data.get(self.add_prefix("curso"))
            else:
                selected_course = getattr(self.instance, "curso_id", None)
            if self.is_bound:
                field_name = self.add_prefix("cursos")
                if hasattr(self.data, "getlist"):
                    selected_extra_courses = self.data.getlist(field_name)
                else:
                    selected_extra_courses = self.data.get(field_name, [])
                    if not isinstance(selected_extra_courses, (list, tuple)):
                        selected_extra_courses = [selected_extra_courses]
            elif self.instance.pk:
                selected_extra_courses = self.instance.cursos.values_list(
                    "pk", flat=True
                )
            else:
                selected_extra_courses = []
            selected_course_ids = list(selected_extra_courses)
            if selected_course:
                selected_course_ids.append(selected_course)
            if selected_course_ids:
                student_courses = assigned_courses.filter(pk__in=selected_course_ids)
            else:
                student_courses = assigned_courses
            self.fields["students"].queryset = User.objects.filter(
                rol=student_role,
                is_active=True,
                cursos__in=student_courses,
            ).distinct()

        self.fields["cursos"].choices = grouped_course_choices(
            self.fields["cursos"].queryset
        )
        if self.instance.pk:
            initial_courses = list(self.instance.cursos.values_list("pk", flat=True))
            if self.instance.curso_id and self.instance.curso_id not in initial_courses:
                initial_courses.append(self.instance.curso_id)
            self.fields["cursos"].initial = initial_courses

    def clean(self):
        cleaned_data = super().clean()
        materia = cleaned_data.get("materia")
        cursos = list(cleaned_data.get("cursos", ()))
        curso = cursos[0] if cursos else cleaned_data.get("curso")
        if curso and not cursos:
            cursos = [curso]
            cleaned_data["cursos"] = cursos
        if curso:
            cleaned_data["curso"] = curso
            self.instance.curso = curso
        else:
            self.add_error("cursos", "Selecciona al menos un curso destino.")
        if (
            self.docente
            and self.docente.rol == User.Role.TEACHER
            and materia
            and curso
            and not AsignacionDocente.objects.filter(
            docente=self.docente,
            materia=materia,
            curso=curso,
            activo=True,
            ).exists()
        ):
            self.add_error("curso", "No tienes asignada esa materia en el curso seleccionado.")
        if self.docente and self.docente.rol == User.Role.TEACHER and materia:
            unassigned_courses = [
                course
                for course in cursos
                if not AsignacionDocente.objects.filter(
                    docente=self.docente,
                    materia=materia,
                    curso=course,
                    activo=True,
                ).exists()
            ]
            if unassigned_courses:
                self.add_error(
                    "cursos",
                    "No tienes asignadas todas las materias y cursos seleccionados.",
                )
        return cleaned_data

    class Meta:
        model = Exam
        fields = [
            "materia",
            "curso",
            "cursos",
            "title",
            "description",
            "duration_minutes",
            "available_from",
            "available_until",
            "published",
            "results_visible",
            "students",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "available_from": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "available_until": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "students": forms.SelectMultiple(attrs={"size": 6}),
        }


class TareaForm(forms.ModelForm):
    class Meta:
        model = Tarea
        fields = [
            "curso",
            "materia",
            "titulo",
            "descripcion",
            "trimestre",
            "parcial",
            "fecha_entrega",
            "peso_porcentual",
            "archivo_adjunto",
            "activo",
        ]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 3, "placeholder": "Instrucciones detalladas de la tarea..."}),
            "fecha_entrega": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "peso_porcentual": forms.NumberInput(attrs={"step": "0.1", "min": "0.1", "max": "100"}),
        }

    def __init__(self, *args, docente=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.docente = docente
        if docente:
            if not (docente.is_superuser or getattr(docente, "rol", "") == "ADMIN"):
                assignments = AsignacionDocente.objects.filter(docente=docente, activo=True)
                self.fields["curso"].queryset = Curso.objects.filter(asignaciones__in=assignments).distinct()
                self.fields["materia"].queryset = Materia.objects.filter(asignaciones__in=assignments).distinct()

    def clean(self):
        cleaned_data = super().clean()
        curso = cleaned_data.get("curso")
        materia = cleaned_data.get("materia")
        if self.docente and curso and materia:
            if not (self.docente.is_superuser or getattr(self.docente, "rol", "") == "ADMIN"):
                assigned = AsignacionDocente.objects.filter(
                    docente=self.docente,
                    materia=materia,
                    curso=curso,
                    activo=True,
                ).exists()
                if not assigned:
                    raise forms.ValidationError("No tienes asignada esa materia en el curso seleccionado.")
        return cleaned_data


class EntregaTareaForm(forms.ModelForm):
    class Meta:
        model = EntregaTarea
        fields = ["archivo", "comentario"]
        widgets = {
            "comentario": forms.Textarea(attrs={"rows": 3, "placeholder": "Comentarios o notas de entrega..."}),
        }

    def clean_archivo(self):
        archivo = self.cleaned_data.get("archivo")
        if not archivo and not self.instance.archivo:
            raise forms.ValidationError("Debes adjuntar un archivo para realizar la entrega.")
        return archivo


class CalificarEntregaForm(forms.ModelForm):
    class Meta:
        model = EntregaTarea
        fields = ["calificacion", "retroalimentacion"]
        widgets = {
            "calificacion": forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "10"}),
            "retroalimentacion": forms.Textarea(attrs={"rows": 3, "placeholder": "Observaciones y retroalimentación institucional..."}),
        }


class InsumoCalificacionForm(forms.ModelForm):
    class Meta:
        model = InsumoCalificacion
        fields = ["curso", "materia", "nombre", "tipo", "trimestre", "parcial", "periodo", "ponderacion", "publicado"]
        widgets = {
            "ponderacion": forms.NumberInput(attrs={"step": "0.01", "min": "0.01", "max": "100"}),
            "periodo": forms.TextInput(attrs={"placeholder": "Ej: Trimestre 1 - Parcial 1"}),
        }

    def __init__(self, *args, docente=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.docente = docente
        if docente:
            if not (docente.is_superuser or getattr(docente, "rol", "") == "ADMIN"):
                assignments = AsignacionDocente.objects.filter(docente=docente, activo=True)
                self.fields["curso"].queryset = Curso.objects.filter(asignaciones__in=assignments).distinct()
                self.fields["materia"].queryset = Materia.objects.filter(asignaciones__in=assignments).distinct()
