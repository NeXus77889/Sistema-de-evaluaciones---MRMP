from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, RequestFactory
from django.urls import reverse
from apps.usuarios.models import User
from apps.evaluaciones.models import Curso, Materia, AsignacionDocente
from .models import (
    Mensaje,
    LecturaMensaje,
    validar_adjunto_mensajeria,
    ESTUDIANTE_PUEDE_ESCRIBIR_A_ADMINISTRATIVOS,
)
from .forms import MensajeDocenteForm, MensajeEstudianteForm, MensajeAdminForm
from .context_processors import unread_mensajes_count


class MensajeriaTestCase(TestCase):
    def setUp(self):
        # Crear usuarios
        self.admin = User.objects.create_superuser(
            username="admin1",
            email="admin@mrmp.edu.ec",
            password="pass",
            first_name="Admin",
            last_name="General",
        )
        self.docente1 = User.objects.create_user(
            username="doc1",
            email="doc1@mrmp.edu.ec",
            password="pass",
            first_name="Docente",
            last_name="Uno",
            rol=User.Role.TEACHER,
        )
        self.docente2 = User.objects.create_user(
            username="doc2",
            email="doc2@mrmp.edu.ec",
            password="pass",
            first_name="Docente",
            last_name="Dos",
            rol=User.Role.TEACHER,
        )
        self.estudiante1 = User.objects.create_user(
            username="est1",
            email="est1@mrmp.edu.ec",
            password="pass",
            first_name="Estudiante",
            last_name="Uno",
            rol=User.Role.STUDENT,
        )
        self.estudiante2 = User.objects.create_user(
            username="est2",
            email="est2@mrmp.edu.ec",
            password="pass",
            first_name="Estudiante",
            last_name="Dos",
            rol=User.Role.STUDENT,
        )

        # Cursos y materias
        self.curso_a = Curso.objects.create(nombre="Tercero BGU A", codigo="3BGU-A")
        self.curso_b = Curso.objects.create(nombre="Tercero BGU B", codigo="3BGU-B")
        self.materia = Materia.objects.create(nombre="Matemática")

        # Asignar estudiantes
        self.curso_a.estudiantes.add(self.estudiante1)
        self.curso_b.estudiantes.add(self.estudiante2)

        # Asignar docente1 solo al curso_a
        self.asig1 = AsignacionDocente.objects.create(
            docente=self.docente1,
            materia=self.materia,
            curso=self.curso_a,
            activo=True,
        )

    def test_creacion_mensaje_individual_y_lectura(self):
        """Un mensaje individual genera automáticamente el registro LecturaMensaje como no leído."""
        msg = Mensaje.objects.create(
            remitente=self.docente1,
            destinatario=self.estudiante1,
            tipo_destino=Mensaje.TIPO_INDIVIDUAL,
            motivo="Bienvenida",
            cuerpo="Hola estudiante 1",
        )
        lecturas = LecturaMensaje.objects.filter(mensaje=msg)
        self.assertEqual(lecturas.count(), 1)
        lectura = lecturas.first()
        self.assertEqual(lectura.destinatario, self.estudiante1)
        self.assertFalse(lectura.leido)

        lectura.marcar_leido()
        lectura.refresh_from_db()
        self.assertTrue(lectura.leido)
        self.assertIsNotNone(lectura.fecha_lectura)

    def test_creacion_mensaje_curso_completo(self):
        """Un mensaje a un curso crea registros de lectura para todos los estudiantes de ese curso."""
        msg = Mensaje.objects.create(
            remitente=self.docente1,
            curso=self.curso_a,
            tipo_destino=Mensaje.TIPO_CURSO,
            motivo="Aviso general",
            cuerpo="Clase suspendida mañana",
        )
        lecturas = LecturaMensaje.objects.filter(mensaje=msg)
        self.assertEqual(lecturas.count(), 1)
        self.assertEqual(lecturas.first().destinatario, self.estudiante1)

    def test_form_docente_valida_solo_estudiantes_de_sus_cursos(self):
        """El docente no puede enviar mensajes a estudiantes de cursos que no enseña."""
        # Intento con estudiante de otro curso
        form_invalido = MensajeDocenteForm(
            data={
                "tipo_destino": Mensaje.TIPO_INDIVIDUAL,
                "destinatario": self.estudiante2.pk,
                "motivo": "Prueba",
                "cuerpo": "Prueba cuerpo",
            },
            user=self.docente1,
        )
        self.assertFalse(form_invalido.is_valid())
        self.assertIn("destinatario", form_invalido.errors)

        # Intento con estudiante de su curso
        form_valido = MensajeDocenteForm(
            data={
                "tipo_destino": Mensaje.TIPO_INDIVIDUAL,
                "destinatario": self.estudiante1.pk,
                "motivo": "Prueba",
                "cuerpo": "Prueba cuerpo",
            },
            user=self.docente1,
        )
        self.assertTrue(form_valido.is_valid())

    def test_form_estudiante_valida_solo_docentes_asignados(self):
        """El estudiante solo puede escribir a docentes asignados a su curso."""
        # Intento con docente no asignado
        form_invalido = MensajeEstudianteForm(
            data={
                "destinatario": self.docente2.pk,
                "motivo": "Duda",
                "cuerpo": "Profesor tengo una duda",
            },
            user=self.estudiante1,
        )
        self.assertFalse(form_invalido.is_valid())
        self.assertIn("destinatario", form_invalido.errors)

        # Intento con su docente asignado
        form_valido = MensajeEstudianteForm(
            data={
                "destinatario": self.docente1.pk,
                "motivo": "Duda",
                "cuerpo": "Profesor tengo una duda",
            },
            user=self.estudiante1,
        )
        self.assertTrue(form_valido.is_valid())

    def test_validador_adjuntos(self):
        """Valida tamaño y tipo de archivo."""
        archivo_valido = SimpleUploadedFile("tarea.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        # No debe lanzar excepción
        validar_adjunto_mensajeria(archivo_valido)

        archivo_invalido = SimpleUploadedFile("malware.exe", b"binary content", content_type="application/x-dosexec")
        with self.assertRaises(ValidationError):
            validar_adjunto_mensajeria(archivo_invalido)

    def test_context_processor_unread_count(self):
        """El context processor cuenta los mensajes no leídos del usuario."""
        rf = RequestFactory()
        req = rf.get("/mensajes/")
        req.user = self.estudiante1

        self.assertEqual(unread_mensajes_count(req)["unread_mensajes_count"], 0)

        # Crear mensaje
        Mensaje.objects.create(
            remitente=self.docente1,
            destinatario=self.estudiante1,
            tipo_destino=Mensaje.TIPO_INDIVIDUAL,
            motivo="Aviso 1",
            cuerpo="Texto",
        )
        self.assertEqual(unread_mensajes_count(req)["unread_mensajes_count"], 1)

    def test_vistas_mensajeria(self):
        """Prueba acceso a las vistas de bandeja, enviados y detalle."""
        self.client.force_login(self.estudiante1)

        msg = Mensaje.objects.create(
            remitente=self.docente1,
            destinatario=self.estudiante1,
            tipo_destino=Mensaje.TIPO_INDIVIDUAL,
            motivo="Examen prox semana",
            cuerpo="Preparar temas 1 al 4",
        )

        # Bandeja de entrada
        resp_inbox = self.client.get(reverse("mensajeria:inbox"))
        self.assertEqual(resp_inbox.status_code, 200)
        self.assertContains(resp_inbox, "Examen prox semana")

        # Detalle de mensaje (debe marcar como leído al visitarlo)
        resp_detail = self.client.get(reverse("mensajeria:detail", kwargs={"mensaje_id": msg.pk}))
        self.assertEqual(resp_detail.status_code, 200)
        self.assertContains(resp_detail, "Preparar temas 1 al 4")

        lectura = LecturaMensaje.objects.get(mensaje=msg, destinatario=self.estudiante1)
        self.assertTrue(lectura.leido)

