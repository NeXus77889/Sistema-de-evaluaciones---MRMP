from django import forms
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from apps.evaluaciones.academic import grouped_course_choices
from apps.evaluaciones.models import AsignacionDocente, Curso, Materia
from apps.evaluaciones.widgets import GroupedCourseCheckboxSelectMultiple
from apps.usuarios.models import User


class TeacherAssignmentFieldsMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cursos"].choices = grouped_course_choices(
            self.fields["cursos"].queryset
        )
        if self.instance.pk and self.instance.rol == User.Role.TEACHER:
            assignments = AsignacionDocente.objects.filter(
                docente=self.instance,
                activo=True,
            )
            self.fields["materias"].initial = assignments.values_list(
                "materia_id", flat=True
            ).distinct()
            self.fields["cursos"].initial = assignments.values_list(
                "curso_id", flat=True
            ).distinct()


class UsuarioCreationForm(TeacherAssignmentFieldsMixin, UserCreationForm):
    materias = forms.ModelMultipleChoiceField(
        queryset=Materia.objects.all(),
        required=False,
        label="Materias",
        help_text="Se crearán las combinaciones con los cursos seleccionados.",
        widget=forms.CheckboxSelectMultiple,
    )
    cursos = forms.ModelMultipleChoiceField(
        queryset=Curso.objects.all(),
        required=False,
        label="Cursos y paralelos",
        help_text="Se crearán las combinaciones con las materias seleccionadas.",
        widget=GroupedCourseCheckboxSelectMultiple,
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username",
            "email",
            "first_name",
            "last_name",
            "rol",
            "identification",
            "debe_cambiar_password",
            "materias",
            "cursos",
        )


class UsuarioChangeForm(TeacherAssignmentFieldsMixin, UserChangeForm):
    materias = forms.ModelMultipleChoiceField(
        queryset=Materia.objects.all(),
        required=False,
        label="Materias",
        help_text="Se crearán las combinaciones con los cursos seleccionados.",
        widget=forms.CheckboxSelectMultiple,
    )
    cursos = forms.ModelMultipleChoiceField(
        queryset=Curso.objects.all(),
        required=False,
        label="Cursos y paralelos",
        help_text="Se crearán las combinaciones con las materias seleccionadas.",
        widget=GroupedCourseCheckboxSelectMultiple,
    )

    class Meta:
        model = User
        fields = "__all__"