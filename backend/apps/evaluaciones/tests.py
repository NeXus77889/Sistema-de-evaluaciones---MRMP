from django.contrib import admin
from django.test import Client, TestCase
from django.urls import reverse

from apps.evaluaciones.academic import format_course_name, grouped_course_choices
from apps.evaluaciones.models import AsignacionDocente, Curso, Materia
from apps.usuarios.models import User


class CourseNomenclatureAndAdminTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="admin_test",
            email="admin@uepmrmp.edu.ec",
            password="AdminPassword123!",
            identification="0999999999",
            rol=User.Role.ADMINISTRATOR,
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
