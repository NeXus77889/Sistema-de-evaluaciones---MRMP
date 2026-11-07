from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.admin import UserAdmin
from django.utils.crypto import get_random_string
from django.contrib.admin import SimpleListFilter

# Importaciones relativas dentro del mismo módulo
from apps.evaluaciones.academic import LEVEL_LABELS, course_level, course_sort_key
from apps.evaluaciones.models import AsignacionDocente, Curso
from .forms import UsuarioChangeForm, UsuarioCreationForm
from .models import User


class StudentCourseFilter(SimpleListFilter):
    title = "curso y paralelo"
    parameter_name = "curso"

    def lookups(self, request, model_admin):
        if request.GET.get("rol__exact") != User.Role.STUDENT:
            return ()
        courses = sorted(Curso.objects.all(), key=course_sort_key)
        return [
            (
                course.pk,
                f"{LEVEL_LABELS[course_level(course)]}: {str(course) if any(term in course.nombre.lower() for term in ('curso', 'informatica', 'ciencias', 'contabilidad')) else course.nombre} ({course.codigo})",
            )
            for course in courses
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(
                rol=User.Role.STUDENT,
                cursos__pk=self.value(),
            ).distinct()
        return queryset


class StudentLevelFilter(SimpleListFilter):
    title = "nivel educativo"
    parameter_name = "nivel_educativo"

    def lookups(self, request, model_admin):
        if request.GET.get("rol__exact") != User.Role.STUDENT:
            return ()
        return tuple(LEVEL_LABELS.items())

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        course_ids = [
            course.pk
            for course in Curso.objects.all()
            if course_level(course) == self.value()
        ]
        return queryset.filter(
            rol=User.Role.STUDENT,
            cursos__pk__in=course_ids,
        ).distinct()


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    form = UsuarioChangeForm
    add_form = UsuarioCreationForm
    list_display = ("username", "full_name", "email", "rol", "is_active")
    list_filter = (
        "rol",
        "is_active",
        "is_staff",
        StudentLevelFilter,
        StudentCourseFilter,
    )
    search_fields = ("username", "first_name", "last_name", "email")
    ordering = ("username",)
    actions = ("reset_temporary_password",)
    fieldsets = UserAdmin.fieldsets + (
        ("Perfil", {"fields": ("rol", "identification", "debe_cambiar_password")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "password1",
                    "password2",
                    "email",
                    "first_name",
                    "last_name",
                    "rol",
                    "identification",
                    "debe_cambiar_password",
                ),
            },
        ),
        (
            "Asignaciones docentes",
            {
                "fields": ("materias", "cursos"),
                "description": "Se guardará una asignación normalizada por cada combinación seleccionada.",
            },
        ),
    )

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj is None:
            return fieldsets
        if obj.rol == User.Role.TEACHER:
            return fieldsets + (
                (
                    "Asignaciones docentes",
                    {
                        "fields": ("materias", "cursos"),
                        "description": "Se guardará una asignación normalizada por cada combinación seleccionada.",
                    },
                ),
            )
        return fieldsets

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        teacher = form.instance
        if teacher.rol != User.Role.TEACHER:
            AsignacionDocente.objects.filter(docente=teacher, activo=True).update(
                activo=False
            )
            return

        selected_subjects = form.cleaned_data.get("materias", ())
        selected_courses = form.cleaned_data.get("cursos", ())
        desired_pairs = {
            (subject.pk, course.pk)
            for subject in selected_subjects
            for course in selected_courses
        }
        current_assignments = AsignacionDocente.objects.filter(docente=teacher)
        for assignment in current_assignments:
            is_selected = (assignment.materia_id, assignment.curso_id) in desired_pairs
            if assignment.activo != is_selected:
                assignment.activo = is_selected
                assignment.save(update_fields=["activo"])

        existing_pairs = set(
            current_assignments.values_list("materia_id", "curso_id")
        )
        for subject_id, course_id in desired_pairs - existing_pairs:
            AsignacionDocente.objects.get_or_create(
                docente=teacher,
                materia_id=subject_id,
                curso_id=course_id,
                defaults={"activo": True},
            )

    @admin.display(description="Nombre")
    def full_name(self, user):
        return user.get_full_name()

    @admin.action(description="Restablecer contraseña a clave temporal")
    def reset_temporary_password(self, request, queryset):
        credentials = []
        for user in queryset:
            temporary_password = get_random_string(14)
            user.set_password(temporary_password)
            user.debe_cambiar_password = True
            user.save(update_fields=["password", "debe_cambiar_password"])
            credentials.append(f"{user.username}: {temporary_password}")
        self.message_user(
            request,
            "Claves temporales: " + "; ".join(credentials),
            level=messages.WARNING,
        )