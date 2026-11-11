from django import forms
from django.contrib.auth import get_user_model
from apps.evaluaciones.models import AsignacionDocente, Curso
from .models import (
    Mensaje,
    ESTUDIANTE_PUEDE_ESCRIBIR_A_ADMINISTRATIVOS,
    validar_adjunto_mensajeria,
)

User = get_user_model()


class MensajeDocenteForm(forms.ModelForm):
    tipo_destino = forms.ChoiceField(
        choices=Mensaje.TIPOS_DESTINO,
        widget=forms.Select(attrs={"class": "form-control", "id": "id_tipo_destino"}),
        label="Enviar a",
    )
    curso = forms.ModelChoiceField(
        queryset=Curso.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-control", "id": "id_curso"}),
        label="Curso / Paralelo",
    )
    destinatario = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-control", "id": "id_destinatario"}),
        label="Estudiante",
    )

    class Meta:
        model = Mensaje
        fields = ["tipo_destino", "curso", "destinatario", "motivo", "cuerpo", "adjunto"]
        widgets = {
            "motivo": forms.TextInput(attrs={"class": "form-control", "placeholder": "Asunto del mensaje"}),
            "cuerpo": forms.Textarea(attrs={"class": "form-control", "rows": 5, "placeholder": "Escribe aquí tu mensaje..."}),
            "adjunto": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        self.docente = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        # Solo cursos donde el docente tiene asignación activa
        cursos_ids = (
            AsignacionDocente.objects.filter(docente=self.docente, activo=True)
            .values_list("curso_id", flat=True)
            .distinct()
        )
        self.fields["curso"].queryset = Curso.objects.filter(id__in=cursos_ids)

        # Solo estudiantes de sus cursos activos
        self.fields["destinatario"].queryset = (
            User.objects.filter(
                rol=User.Role.STUDENT,
                cursos__id__in=cursos_ids,
                is_active=True,
            )
            .distinct()
            .order_by("last_name", "first_name")
        )

    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get("tipo_destino")
        curso = cleaned_data.get("curso")
        destinatario = cleaned_data.get("destinatario")

        cursos_permitidos = set(
            AsignacionDocente.objects.filter(docente=self.docente, activo=True)
            .values_list("curso_id", flat=True)
        )

        if tipo == Mensaje.TIPO_CURSO:
            if not curso:
                self.add_error("curso", "Debes seleccionar un curso de destino.")
            elif curso.id not in cursos_permitidos:
                self.add_error("curso", "No tienes asignación docente activa en este curso.")
            cleaned_data["destinatario"] = None

        elif tipo == Mensaje.TIPO_INDIVIDUAL:
            if not destinatario:
                self.add_error("destinatario", "Debes seleccionar un estudiante destinatario.")
            else:
                cursos_estudiante = set(destinatario.cursos.values_list("id", flat=True))
                if not (cursos_estudiante & cursos_permitidos):
                    self.add_error("destinatario", "El estudiante seleccionado no pertenece a ninguno de tus cursos.")
            cleaned_data["curso"] = None

        return cleaned_data


class MensajeEstudianteForm(forms.ModelForm):
    destinatario = forms.ModelChoiceField(
        queryset=User.objects.none(),
        widget=forms.Select(attrs={"class": "form-control"}),
        label="Docente destinatario",
    )

    class Meta:
        model = Mensaje
        fields = ["destinatario", "motivo", "cuerpo", "adjunto"]
        widgets = {
            "motivo": forms.TextInput(attrs={"class": "form-control", "placeholder": "Asunto del mensaje"}),
            "cuerpo": forms.Textarea(attrs={"class": "form-control", "rows": 5, "placeholder": "Escribe tu consulta o mensaje..."}),
            "adjunto": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        self.estudiante = kwargs.pop("user")
        super().__init__(*args, **kwargs)

        cursos_estudiante = self.estudiante.cursos.values_list("id", flat=True)
        docentes_ids = (
            AsignacionDocente.objects.filter(curso_id__in=cursos_estudiante, activo=True)
            .values_list("docente_id", flat=True)
            .distinct()
        )

        qs = User.objects.filter(id__in=docentes_ids, is_active=True)
        if ESTUDIANTE_PUEDE_ESCRIBIR_A_ADMINISTRATIVOS:
            admin_ids = User.objects.filter(rol=User.Role.ADMINISTRATOR, is_active=True).values_list("id", flat=True)
            qs = User.objects.filter(id__in=set(docentes_ids) | set(admin_ids), is_active=True)

        self.fields["destinatario"].queryset = qs.order_by("last_name", "first_name")

    def clean(self):
        cleaned_data = super().clean()
        destinatario = cleaned_data.get("destinatario")
        if destinatario:
            cursos_estudiante = set(self.estudiante.cursos.values_list("id", flat=True))
            docentes_validos = set(
                AsignacionDocente.objects.filter(curso_id__in=cursos_estudiante, activo=True)
                .values_list("docente_id", flat=True)
            )
            es_docente_propio = destinatario.id in docentes_validos
            es_admin_permitido = (
                ESTUDIANTE_PUEDE_ESCRIBIR_A_ADMINISTRATIVOS
                and destinatario.rol == User.Role.ADMINISTRATOR
            )
            if not (es_docente_propio or es_admin_permitido):
                self.add_error("destinatario", "Solo puedes enviar mensajes a docentes asignados a tus cursos.")
        return cleaned_data


class MensajeAdminForm(forms.ModelForm):
    tipo_destino = forms.ChoiceField(
        choices=Mensaje.TIPOS_DESTINO,
        widget=forms.Select(attrs={"class": "form-control", "id": "id_tipo_destino"}),
        label="Enviar a",
    )
    curso = forms.ModelChoiceField(
        queryset=Curso.objects.all().order_by("nombre"),
        required=False,
        widget=forms.Select(attrs={"class": "form-control", "id": "id_curso"}),
        label="Curso / Paralelo",
    )
    destinatario = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by("last_name", "first_name"),
        required=False,
        widget=forms.Select(attrs={"class": "form-control", "id": "id_destinatario"}),
        label="Usuario",
    )

    class Meta:
        model = Mensaje
        fields = ["tipo_destino", "curso", "destinatario", "motivo", "cuerpo", "adjunto"]
        widgets = {
            "motivo": forms.TextInput(attrs={"class": "form-control", "placeholder": "Asunto oficial"}),
            "cuerpo": forms.Textarea(attrs={"class": "form-control", "rows": 5, "placeholder": "Escribe el comunicado..."}),
            "adjunto": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        self.admin = kwargs.pop("user")
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get("tipo_destino")
        curso = cleaned_data.get("curso")
        destinatario = cleaned_data.get("destinatario")

        if tipo == Mensaje.TIPO_CURSO:
            if not curso:
                self.add_error("curso", "Debes seleccionar un curso de destino.")
            cleaned_data["destinatario"] = None
        elif tipo == Mensaje.TIPO_INDIVIDUAL:
            if not destinatario:
                self.add_error("destinatario", "Debes seleccionar un usuario destinatario.")
            cleaned_data["curso"] = None
        return cleaned_data

