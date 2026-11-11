import io
from datetime import timedelta
from decimal import Decimal
import docx
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.evaluaciones.academic import (
    format_action_repr,
    format_course_name,
    grouped_course_choices,
)
from apps.evaluaciones.docx_import import parse_docx_questions
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
from apps.usuarios.services import importar_nomina


class CourseNomenclatureAndAdminTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="admin_test",
            email="admin@uepmrmp.edu.ec",
            password="AdminPassword123!",
            identification="0999999999",
            rol=User.Role.ADMINISTRATOR,
            debe_cambiar_password=False,
        )
        self.client = Client()

    def test_course_nomenclature_standardization_rules(self):
        """
        Regla Obligatoria de Nomenclatura:
        - Prohibido usar frases descriptivas largas como 'tercer curso de informática' o 'tercer curso de ciencias'.
        - Obligatorio formato estandarizado: '3º BGU [Especialidad] [Paralelo]'.
        - Asignación automática de paralelo 'A' si no tiene especificación B.
        """
        cases = [
            ("tercer curso de informática", "3º BGU Informática A"),
            ("tercer curso de ciencias", "3º BGU Ciencias A"),
            ("tercer curso de contabilidad", "3º BGU Contabilidad A"),
            ("Segundo Curso Informática - Paralelo A", "2º BGU Informática A"),
            ("3º BGU Informática A", "3º BGU Informática A"),
            ("3º BGU Informática", "3º BGU Informática A"),
            ("3º BGU Ciencias", "3º BGU Ciencias A"),
            ("3º BGU Contabilidad", "3º BGU Contabilidad A"),
            ("3º BGU Informática B", "3º BGU Informática B"),
            ("Tercero de Bachillerato Ciencias B", "3º BGU Ciencias B"),
            ("Primer Grado Paralelo - Paralelo A", "1º EGB A"),
            ("segundo curso de ciencias", "2º BGU Ciencias A"),
            ("Segundo EGB B", "2º EGB B"),
            ("Primero A", "1º A"),
            ("Inicial 1", "Inicial 1"),
            ("Inicial 2", "Inicial 2"),
        ]

        for input_name, expected_name in cases:
            with self.subTest(input_name=input_name):
                self.assertEqual(format_course_name(input_name), expected_name)

    def test_curso_model_str_returns_standardized_representation(self):
        curso1 = Curso.objects.create(nombre="tercer curso de informática", codigo="3-INF")
        curso2 = Curso.objects.create(nombre="tercer curso de ciencias", codigo="3-CIEN")
        curso3 = Curso.objects.create(nombre="Segundo Curso Informática - Paralelo A", codigo="2-INF-A")

        self.assertEqual(str(curso1), "3º BGU Informática A")
        self.assertEqual(str(curso2), "3º BGU Ciencias A")
        self.assertEqual(str(curso3), "2º BGU Informática A")

    def test_grouped_course_choices_uses_standardized_labels(self):
        curso = Curso.objects.create(nombre="tercer curso de informática", codigo="3-INF")
        choices = grouped_course_choices([curso])
        labels = [choice_text for _, group_choices in choices for _, choice_text in group_choices]
        self.assertIn("3º BGU Informática A", labels)
        self.assertNotIn("tercer curso de informática", labels)

    def test_asignacion_docente_str_includes_standardized_course(self):
        docente = User.objects.create_user(
            username="docente_test",
            password="DocPass123!",
            rol=User.Role.TEACHER,
            first_name="Profesor",
            last_name="Ejemplo",
        )
        materia = Materia.objects.create(nombre="Informática Aplicada", codigo="INF-APP")
        curso = Curso.objects.create(nombre="tercer curso de informática", codigo="3-INF")
        asignacion = AsignacionDocente.objects.create(docente=docente, materia=materia, curso=curso)

        self.assertIn("3º BGU Informática A", str(asignacion))
        self.assertNotIn("tercer curso de informática", str(asignacion))

    def test_admin_site_headers_and_titles_configured(self):
        self.assertEqual(
            admin.site.site_header, "Administración Sistema Proctoring — UEPMRMP"
        )
        self.assertEqual(admin.site.site_title, "Sistema Proctoring — UEPMRMP")
        self.assertEqual(admin.site.index_title, "Panel de Control Institucional")

    def test_administracion_and_admin_endpoints(self):
        self.client.force_login(self.admin_user)

        # /admin/
        admin_response = self.client.get("/admin/")
        self.assertEqual(admin_response.status_code, 200)
        self.assertContains(admin_response, "Panel de Control Institucional")
        self.assertContains(admin_response, "Gestión de recursos académicos e institucionales")
        self.assertContains(admin_response, "Unidad Educativa Particular Monseñor Roberto María del Pozo")

        # /administracion/
        adm_response = self.client.get(reverse("administracion"))
        self.assertEqual(adm_response.status_code, 200)
        self.assertContains(adm_response, "Administración")

    def test_format_action_repr_standardization(self):
        repr1 = "Juanito farralas - Biología - Primer Grado Paralelo - Paralelo A"
        repr2 = "Juanito farralas - matemática - Segundo Curso Informática - Paralelo A"
        self.assertEqual(format_action_repr(repr1), "Juanito farralas - Biología - 1º EGB A")
        self.assertEqual(format_action_repr(repr2), "Juanito farralas - matemática - 2º BGU Informática A")


class DocxImportTests(TestCase):
    def test_parse_docx_questions_with_tables_and_paragraphs(self):
        doc = docx.Document()
        doc.add_heading("Examen de Prueba", 0)
        doc.add_paragraph("")  # Empty paragraph

        # Question 1: via paragraphs with checkmark
        p1 = doc.add_paragraph("1. ¿Cuál es el protocolo de red para navegación web segura?")
        doc.add_paragraph("a) FTP")
        doc.add_paragraph("b) HTTP")
        doc.add_paragraph("c) [x] HTTPS")
        doc.add_paragraph("d) Telnet")

        # Question 2: inside a table
        table = doc.add_table(rows=5, cols=1)
        table.rows[0].cells[0].text = "2. ¿Qué componente ejecuta las instrucciones del programa?"
        table.rows[1].cells[0].text = "a) Memoria RAM"
        table.rows[2].cells[0].text = "b) Disco Duro"
        table.rows[3].cells[0].text = "c) CPU *"
        table.rows[4].cells[0].text = "d) Fuente de poder"

        bio = io.BytesIO()
        doc.save(bio)
        bio.seek(0)

        questions = parse_docx_questions(bio)
        self.assertEqual(len(questions), 2)
        q1 = questions[0]
        self.assertIn("navegación web segura", q1["text"])
        self.assertEqual(len(q1["options"]), 4)
        correct_opts = [o["text"] for o in q1["options"] if o["correct"]]
        self.assertEqual(correct_opts, ["HTTPS"])

        q2 = questions[1]
        self.assertIn("ejecuta las instrucciones", q2["text"])
        self.assertEqual(len(q2["options"]), 4)
        correct_opts2 = [o["text"] for o in q2["options"] if o["correct"]]
        self.assertEqual(correct_opts2, ["CPU"])


class TareasAndEntregasRBACAndLifecycleTests(TestCase):
    def setUp(self):
        self.docente = User.objects.create_user(
            username="docente_tareas",
            email="docente_tareas@uepmrmp.edu.ec",
            password="Password123!",
            rol=User.Role.TEACHER,
            first_name="Profesor",
            last_name="García",
            identification="0102030405",
            debe_cambiar_password=False,
        )
        self.otro_docente = User.objects.create_user(
            username="otro_docente",
            email="otro_docente@uepmrmp.edu.ec",
            password="Password123!",
            rol=User.Role.TEACHER,
            identification="0102030406",
            debe_cambiar_password=False,
        )
        self.estudiante = User.objects.create_user(
            username="estudiante_1",
            email="estudiante_1@uepmrmp.edu.ec",
            password="Password123!",
            rol=User.Role.STUDENT,
            first_name="Estudiante",
            last_name="Uno",
            identification="0911223344",
            debe_cambiar_password=False,
        )
        self.materia = Materia.objects.create(nombre="Física", codigo="FIS-1")
        self.curso = Curso.objects.create(nombre="Segundo Curso Informática - Paralelo A", codigo="2-INF-A")
        self.curso.estudiantes.add(self.estudiante)

        # Asignación válida
        self.asignacion = AsignacionDocente.objects.create(
            docente=self.docente,
            materia=self.materia,
            curso=self.curso,
            activo=True,
        )
        self.client = Client()

    def test_docente_cannot_create_tarea_for_unassigned_course(self):
        tarea = Tarea(
            docente=self.otro_docente,  # No asignado a este curso/materia
            materia=self.materia,
            curso=self.curso,
            titulo="Tarea No Autorizada",
            fecha_entrega=timezone.now() + timedelta(days=2),
            peso_porcentual=Decimal("15.00"),
        )
        with self.assertRaises(ValidationError):
            tarea.save()

    def test_docente_creates_valid_tarea(self):
        tarea = Tarea.objects.create(
            docente=self.docente,
            materia=self.materia,
            curso=self.curso,
            titulo="Leyes de Newton",
            descripcion="Resolver guía de ejercicios",
            fecha_entrega=timezone.now() + timedelta(days=2),
            peso_porcentual=Decimal("10.00"),
        )
        self.assertEqual(tarea.peso_porcentual, Decimal("10.00"))
        self.assertEqual(str(tarea.curso), "2º BGU Informática A")

    def test_estudiante_submits_tarea_on_time_and_late(self):
        tarea_futura = Tarea.objects.create(
            docente=self.docente,
            materia=self.materia,
            curso=self.curso,
            titulo="Tarea Futura",
            fecha_entrega=timezone.now() + timedelta(days=2),
        )

        dummy_file = SimpleUploadedFile("deber.pdf", b"Contenido del trabajo escolar", content_type="application/pdf")

        # Entrega a tiempo
        self.client.force_login(self.estudiante)
        url = reverse("estudiante-tarea-entrega", args=[tarea_futura.pk])
        resp = self.client.post(url, {"archivo": dummy_file, "comentario": "Entrega puntual"})
        self.assertEqual(resp.status_code, 302)

        entrega = EntregaTarea.objects.get(tarea=tarea_futura, estudiante=self.estudiante)
        self.assertEqual(entrega.estado, EntregaTarea.ESTADO_ENTREGADO)

        # Tarea ya vencida -> entrega atrasada
        tarea_vencida = Tarea.objects.create(
            docente=self.docente,
            materia=self.materia,
            curso=self.curso,
            titulo="Tarea Pasada",
            fecha_entrega=timezone.now() - timedelta(days=2),
        )
        dummy_file2 = SimpleUploadedFile("deber_tarde.pdf", b"Contenido tardio", content_type="application/pdf")
        url_vencida = reverse("estudiante-tarea-entrega", args=[tarea_vencida.pk])
        resp_vencida = self.client.post(url_vencida, {"archivo": dummy_file2, "comentario": "Entrega tardía"})
        self.assertEqual(resp_vencida.status_code, 302)

        entrega_tardia = EntregaTarea.objects.get(tarea=tarea_vencida, estudiante=self.estudiante)
        self.assertEqual(entrega_tardia.estado, EntregaTarea.ESTADO_ATRASADO)

    def test_docente_califica_entrega_and_bounds_validation(self):
        tarea = Tarea.objects.create(
            docente=self.docente,
            materia=self.materia,
            curso=self.curso,
            titulo="Tarea a Calificar",
            fecha_entrega=timezone.now() + timedelta(days=1),
        )
        entrega = EntregaTarea.objects.create(
            tarea=tarea,
            estudiante=self.estudiante,
            estado=EntregaTarea.ESTADO_ENTREGADO,
        )

        self.client.force_login(self.docente)
        url = reverse("docente-tarea-detalle", args=[tarea.pk])

        # Nota válida: 9.50
        resp = self.client.post(url, {
            "calificar_entrega_id": entrega.pk,
            "calificacion": "9.50",
            "retroalimentacion": "Excelente desarrollo",
        })
        self.assertEqual(resp.status_code, 302)
        entrega.refresh_from_db()
        self.assertEqual(entrega.calificacion, Decimal("9.50"))
        self.assertEqual(entrega.retroalimentacion, "Excelente desarrollo")

        # Nota fuera de rango: 12.00
        resp_invalid = self.client.post(url, {
            "calificar_entrega_id": entrega.pk,
            "calificacion": "12.00",
        })
        self.assertEqual(resp_invalid.status_code, 302)
        entrega.refresh_from_db()
        self.assertEqual(entrega.calificacion, Decimal("9.50"))  # Conserva la anterior


class CalificacionesRunachayTests(TestCase):
    def setUp(self):
        self.docente = User.objects.create_user(
            username="docente_runachay",
            email="docente_runachay@uepmrmp.edu.ec",
            password="DocPass123!",
            rol=User.Role.TEACHER,
            identification="0808080808",
            debe_cambiar_password=False,
        )
        self.estudiante = User.objects.create_user(
            username="estudiante_runachay",
            email="estudiante_runachay@uepmrmp.edu.ec",
            password="EstPass123!",
            rol=User.Role.STUDENT,
            first_name="Anita",
            last_name="Perez",
            identification="0707070707",
            debe_cambiar_password=False,
        )
        self.materia = Materia.objects.create(nombre="Química", codigo="QUI-1")
        self.curso = Curso.objects.create(nombre="3º BGU Ciencias A", codigo="3-BGU-CIEN-A")
        self.curso.estudiantes.add(self.estudiante)

        AsignacionDocente.objects.create(
            docente=self.docente,
            materia=self.materia,
            curso=self.curso,
            activo=True,
        )
        self.client = Client()

    def test_runachay_insumos_and_weighted_average_calculation(self):
        # Insumo 1: 35%, Insumo 2: 35%, Evaluacion: 30%
        i1 = InsumoCalificacion.objects.create(
            curso=self.curso,
            materia=self.materia,
            docente=self.docente,
            nombre="Insumo 1 (Tareas / Actividades)",
            tipo=InsumoCalificacion.TIPO_INSUMO_1,
            ponderacion=Decimal("35.00"),
            publicado=True,
        )
        i2 = InsumoCalificacion.objects.create(
            curso=self.curso,
            materia=self.materia,
            docente=self.docente,
            nombre="Insumo 2 (Lecciones / Proyectos)",
            tipo=InsumoCalificacion.TIPO_INSUMO_2,
            ponderacion=Decimal("35.00"),
            publicado=True,
        )
        ie = InsumoCalificacion.objects.create(
            curso=self.curso,
            materia=self.materia,
            docente=self.docente,
            nombre="Evaluación del Parcial",
            tipo=InsumoCalificacion.TIPO_EVALUACION,
            ponderacion=Decimal("30.00"),
            publicado=True,
        )

        # Notas: I1 = 10.00, I2 = 8.00, IE = 9.00
        # Promedio: (10 * 35 + 8 * 35 + 9 * 30) / 100 = (350 + 280 + 270) / 100 = 900 / 100 = 9.00
        RegistroCalificacion.objects.create(insumo=i1, estudiante=self.estudiante, nota=Decimal("10.00"))
        RegistroCalificacion.objects.create(insumo=i2, estudiante=self.estudiante, nota=Decimal("8.00"))
        RegistroCalificacion.objects.create(insumo=ie, estudiante=self.estudiante, nota=Decimal("9.00"))

        # El estudiante visualiza su boletin
        self.client.force_login(self.estudiante)
        resp = self.client.get(reverse("estudiante-calificaciones-boletin"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "9.0")
        self.assertContains(resp, "Domina los aprendizajes (DAR)")

    def test_runachay_publication_visibility_flag(self):
        insumo = InsumoCalificacion.objects.create(
            curso=self.curso,
            materia=self.materia,
            docente=self.docente,
            nombre="Insumo Borrador",
            ponderacion=Decimal("100.00"),
            publicado=False,  # En modo borrador
        )
        RegistroCalificacion.objects.create(insumo=insumo, estudiante=self.estudiante, nota=Decimal("10.00"))

        # El estudiante no debe ver notas si no están publicadas
        self.client.force_login(self.estudiante)
        resp = self.client.get(reverse("estudiante-calificaciones-boletin"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Aún no hay calificaciones publicadas oficialmente")
        self.assertNotContains(resp, "Insumo Borrador")

        # Docente publica calificaciones
        self.client.force_login(self.docente)
        url_docente = f"{reverse('docente-calificaciones-matrix')}?curso={self.curso.pk}&materia={self.materia.pk}"
        resp_pub = self.client.post(url_docente, {"action": "publish_all"})
        self.assertEqual(resp_pub.status_code, 302)

        insumo.refresh_from_db()
        self.assertTrue(insumo.publicado)

        # Ahora el estudiante sí las ve
        self.client.force_login(self.estudiante)
        resp2 = self.client.get(reverse("estudiante-calificaciones-boletin"))
        self.assertContains(resp2, "Insumo Borrador")
        self.assertContains(resp2, "10.0")

    def test_tarea_asegurar_insumo_and_bidirectional_sync(self):
        tarea = Tarea.objects.create(
            curso=self.curso,
            materia=self.materia,
            docente=self.docente,
            titulo="Investigación de Álgebra",
            trimestre=2,
            parcial=1,
            fecha_entrega=timezone.now() + timedelta(days=2),
            peso_porcentual=Decimal("15.00"),
        )
        self.assertIsNotNone(tarea.insumo)
        self.assertEqual(tarea.insumo.trimestre, 2)
        self.assertEqual(tarea.insumo.parcial, 1)
        self.assertEqual(tarea.insumo.ponderacion, Decimal("15.00"))

        # Calificar entrega desde docente_tarea_detalle
        self.client.force_login(self.docente)
        url_detalle = reverse("docente-tarea-detalle", args=[tarea.pk])
        resp = self.client.post(
            url_detalle,
            {
                "calificar_estudiante_id": self.estudiante.pk,
                "calificacion": "9.50",
                "retroalimentacion": "Excelente trabajo",
            },
        )
        self.assertEqual(resp.status_code, 302)

        # Verificar que se creó RegistroCalificacion sincronizado
        registro = RegistroCalificacion.objects.get(insumo=tarea.insumo, estudiante=self.estudiante)
        self.assertEqual(registro.nota, Decimal("9.50"))

        # Modificar nota desde la sábana y verificar sincronización hacia EntregaTarea
        registro.nota = Decimal("8.00")
        registro.save()
        entrega = EntregaTarea.objects.get(tarea=tarea, estudiante=self.estudiante)
        self.assertEqual(entrega.calificacion, Decimal("8.00"))

        # Borrar nota (dejar en blanco) y verificar que se limpia en ambos
        resp_clear = self.client.post(
            url_detalle,
            {
                "calificar_entrega_id": entrega.pk,
                "calificacion": "",
            },
        )
        self.assertEqual(resp_clear.status_code, 302)
        self.assertFalse(RegistroCalificacion.objects.filter(insumo=tarea.insumo, estudiante=self.estudiante).exists())
        entrega.refresh_from_db()
        self.assertIsNone(entrega.calificacion)

    def test_calificaciones_matrix_cell_save_ajax(self):
        insumo = InsumoCalificacion.objects.create(
            curso=self.curso,
            materia=self.materia,
            docente=self.docente,
            nombre="Taller 1",
            trimestre=1,
            parcial=1,
            ponderacion=Decimal("50.00"),
        )
        self.client.force_login(self.docente)
        url_matrix = reverse("docente-calificaciones-matrix") + f"?curso={self.curso.pk}&materia={self.materia.pk}&trimestre=1&parcial=1"

        # Guardar celda vía AJAX
        resp = self.client.post(
            url_matrix,
            {
                "action": "save_single_grade",
                "insumo_id": insumo.pk,
                "estudiante_id": self.estudiante.pk,
                "nota": "9.25",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["nota"], "9.25")
        self.assertTrue(RegistroCalificacion.objects.filter(insumo=insumo, estudiante=self.estudiante, nota=Decimal("9.25")).exists())

        # Validación nota > 10
        resp_invalid = self.client.post(
            url_matrix,
            {
                "action": "save_single_grade",
                "insumo_id": insumo.pk,
                "estudiante_id": self.estudiante.pk,
                "nota": "15.00",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp_invalid.status_code, 400)

    def test_convertir_periodos_command(self):
        from django.core.management import call_command

        insumo_antiguo = InsumoCalificacion.objects.create(
            curso=self.curso,
            materia=self.materia,
            docente=self.docente,
            nombre="Insumo Antiguo",
            periodo="Segundo Quimestre - Parcial 2",
            trimestre=1,
            parcial=1,
        )
        call_command("convertir_periodos")
        insumo_antiguo.refresh_from_db()
        self.assertEqual(insumo_antiguo.trimestre, 2)
        self.assertEqual(insumo_antiguo.parcial, 2)


