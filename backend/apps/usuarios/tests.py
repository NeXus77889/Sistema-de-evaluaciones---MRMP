import os
from io import BytesIO
from io import StringIO
from tempfile import NamedTemporaryFile
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib import admin as django_admin
from django.contrib.auth.hashers import check_password
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.urls import reverse
from openpyxl import Workbook

from apps.evaluaciones.models import AsignacionDocente, Curso, Materia
from apps.usuarios.models import User
from apps.usuarios.services import importar_docentes, importar_nomina


def make_workbook(records):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(
        [
            "identificacion",
            "nombres",
            "apellidos",
            "email",
            "curso_codigo",
            "curso_nombre",
        ]
    )
    for record in records:
        sheet.append(record)
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


class NominaImportTests(TestCase):
    def test_import_detects_shifted_headers_and_normalizes_course_names(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Hoja de matrícula"
        for _ in range(12):
            sheet.append(["Institución educativa"])
        sheet.append(
            ["Cédula estudiante", "Nombres", "Apellidos", "Correo", "Curso"]
        )
        sheet.append([123456789, "ANA MARIA", "PEREZ LOPEZ", "", "Primero A"])
        source = BytesIO()
        workbook.save(source)

        importar_nomina(source, "nomina_desordenada.xlsx")

        course = Curso.objects.get(codigo="1-A")
        self.assertEqual(course.nombre, "1º A")

    def test_institutional_sheet_abbreviation_is_canonicalized(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "1º INF."
        for _ in range(10):
            sheet.append(["Informe institucional"])
        sheet.append(["Nómina de estudiantes del periodo"])
        sheet.append(["Cédula de estudiante", "Nómina de estudiante"])
        sheet.append([123456789, "PEREZ LOPEZ ANA MARIA"])
        source = BytesIO()
        workbook.save(source)

        importar_nomina(source, "nomina_institucional.xlsx")

        course = Curso.objects.get(codigo="1-INF-A")
        self.assertEqual(course.nombre, "1º BGU Informática A")

    def test_import_reuses_course_with_existing_canonical_name(self):
        course = Curso.objects.create(nombre="1º EGB A", codigo="PRIM-GRAD-PARA-A")
        source = make_workbook(
            [("123456789", "ANA MARIA", "PEREZ LOPEZ", "", "1-EGB-A", "1º EGB A")]
        )

        summary = importar_nomina(source, "nomina.xlsx")

        self.assertEqual(Curso.objects.filter(nombre="1º EGB A").count(), 1)
        self.assertEqual(summary["cursos_creados"], 0)
        self.assertEqual(Curso.objects.get(nombre="1º EGB A"), course)

    def test_admin_user_add_form_includes_multi_assignment_selectors(self):
        administrator = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="AdminStrongPass!234",
        )
        Materia.objects.create(nombre="Matemáticas", codigo="MAT")
        Curso.objects.create(nombre="Primero A", codigo="1A")
        self.client.force_login(administrator)

        response = self.client.get(reverse("admin:usuarios_user_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Asignaciones docentes")
        self.assertContains(response, 'name="materias"')
        self.assertContains(response, 'name="cursos"')

    def test_admin_course_filter_is_available_only_for_students(self):
        administrator = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="AdminStrongPass!234",
        )
        first_course = Curso.objects.create(nombre="Primero A", codigo="1A")
        second_course = Curso.objects.create(nombre="Segundo B", codigo="2B")
        first_student = User.objects.create_user(
            username="first-student",
            email="first@example.com",
            password="StrongPass!234",
            rol=User.Role.STUDENT,
        )
        second_student = User.objects.create_user(
            username="second-student",
            email="second@example.com",
            password="StrongPass!234",
            rol=User.Role.STUDENT,
        )
        first_course.estudiantes.add(first_student)
        second_course.estudiantes.add(second_student)
        self.client.force_login(administrator)
        changelist = reverse("admin:usuarios_user_changelist")

        student_filter = self.client.get(
            changelist, {"rol__exact": User.Role.STUDENT}
        )
        filtered_students = self.client.get(
            changelist,
            {"rol__exact": User.Role.STUDENT, "curso": first_course.pk},
        )
        teacher_filter = self.client.get(
            changelist, {"rol__exact": User.Role.TEACHER}
        )

        self.assertContains(student_filter, "curso y paralelo")
        self.assertContains(student_filter, "Primero A (1A)")
        self.assertContains(filtered_students, "first-student")
        self.assertNotContains(filtered_students, "second-student")
        self.assertNotContains(teacher_filter, "curso y paralelo")

    def test_teacher_admin_profile_renders_assignment_inline(self):
        administrator = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="AdminStrongPass!234",
        )
        teacher = User.objects.create_user(
            username="teacher",
            email="teacher@example.com",
            password="StrongPass!234",
            rol=User.Role.TEACHER,
        )
        self.client.force_login(administrator)

        response = self.client.get(
            reverse("admin:usuarios_user_change", args=[teacher.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Asignaciones docentes")
        self.assertContains(response, "Materias")
        self.assertContains(response, "Cursos y paralelos")

    def test_admin_syncs_multiple_teacher_subjects_and_courses_as_pairs(self):
        administrator = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="AdminStrongPass!234",
        )
        teacher = User.objects.create_user(
            username="teacher",
            email="teacher@example.com",
            password="StrongPass!234",
            rol=User.Role.TEACHER,
        )
        biology = Materia.objects.create(nombre="Biología", codigo="BIO")
        mathematics = Materia.objects.create(nombre="Matemáticas", codigo="MAT")
        science_a = Curso.objects.create(nombre="2º Ciencias A", codigo="2CA")
        science_b = Curso.objects.create(nombre="2º Ciencias B", codigo="2CB")
        request = RequestFactory().post("/")
        request.user = administrator
        model_admin = django_admin.site._registry[User]

        selection = SimpleNamespace(
            instance=teacher,
            cleaned_data={
                "materias": [biology, mathematics],
                "cursos": [science_a, science_b],
            },
            save_m2m=lambda: None,
        )
        model_admin.save_related(request, selection, [], change=True)

        assignments = AsignacionDocente.objects.filter(docente=teacher)
        self.assertEqual(assignments.count(), 4)
        self.assertEqual(assignments.filter(activo=True).count(), 4)

        selection.cleaned_data = {
            "materias": [biology],
            "cursos": [science_a],
        }
        model_admin.save_related(request, selection, [], change=True)

        self.assertEqual(assignments.count(), 4)
        self.assertEqual(assignments.filter(activo=True).count(), 1)

    def test_user_save_keeps_username_equal_to_identification(self):
        user = User.objects.create_user(
            username="old-account-name",
            email="identity@example.com",
            password="StrongPass!234",
            identification="0102030405",
        )

        user.first_name = "Actualizado"
        user.save(update_fields=["first_name"])
        user.refresh_from_db()

        self.assertEqual(user.username, "0102030405")

    def test_teacher_import_admin_renders_report_and_downloads_csv(self):
        admin_user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="AdminStrongPass!234",
        )
        Materia.objects.create(nombre="Programación", codigo="PROG")
        Curso.objects.create(nombre="Segundo A", codigo="2A")
        self.client.force_login(admin_user)
        csv_file = SimpleUploadedFile(
            "docentes.csv",
            (
                "Cedula,Apellidos,Nombres,Email,Materia(s),Curso(s)\n"
                "123456789,PEREZ LOPEZ,ANA MARIA,ana@example.com,"
                "Programación,2A\n"
            ).encode(),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("admin:evaluaciones_curso_importar_docentes"),
            {"archivo": csv_file},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Docente")
        self.assertContains(response, "Clave Temporal")
        report_id = response.context["report_id"]
        csv_response = self.client.get(
            reverse(
                "admin:evaluaciones_curso_descargar_reporte_csv",
                kwargs={"report_id": report_id},
            )
        )
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("Clave Temporal", csv_response.content.decode("utf-8-sig"))
        self.assertIn("0123456789", csv_response.content.decode("utf-8-sig"))

    def test_teacher_xlsx_command_requires_password_change(self):
        Materia.objects.create(nombre="Historia", codigo="HIS")
        Curso.objects.create(nombre="Primero A", codigo="1A")
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Cedula", "Apellidos", "Nombres", "Email", "Materia(s)", "Curso(s)"])
        sheet.append(["123456789", "GOMEZ DIAZ", "LUIS", "luis@example.com", "Historia", "1A"])
        source = BytesIO()
        workbook.save(source)

        excel_file = NamedTemporaryFile(suffix=".xlsx", delete=False)
        try:
            excel_file.write(source.getvalue())
            excel_file.close()
            output = StringIO()
            call_command("importar_docentes", excel_file.name, stdout=output)
        finally:
            if os.path.exists(excel_file.name):
                os.unlink(excel_file.name)

        teacher = User.objects.get(identification="0123456789")
        self.assertTrue(teacher.debe_cambiar_password)
        self.assertIn("Claves temporales", output.getvalue())
        self.client.force_login(teacher)
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, reverse("password-change"))

    def test_teacher_csv_import_creates_heterogeneous_assignments(self):
        programming = Materia.objects.create(nombre="Programación", codigo="PROG")
        office = Materia.objects.create(nombre="Aplicaciones Ofimáticas", codigo="OFI")
        technical_course = Curso.objects.create(nombre="2º INF A", codigo="2-INF-A")
        general_course = Curso.objects.create(nombre="2º CIENCIAS B", codigo="2-CIEN-B")
        csv_content = (
            "Cédula,Apellidos,Nombres,Email,Materia(s),Curso(s)\n"
            "123456789,LOPEZ PEREZ,ANA MARIA,ana@example.com,"
            "Programación,2º INF A\n"
            "123456789,LOPEZ PEREZ,ANA MARIA,ana@example.com,"
            "Aplicaciones Ofimáticas,2º CIENCIAS B\n"
        )

        summary = importar_docentes(
            BytesIO(csv_content.encode("utf-8-sig")), "docentes.csv"
        )

        teacher = User.objects.get(identification="0123456789")
        self.assertEqual(teacher.username, "0123456789")
        self.assertEqual(teacher.rol, User.Role.TEACHER)
        self.assertTrue(teacher.debe_cambiar_password)
        self.assertEqual(teacher.first_name, "ANA MARIA")
        self.assertEqual(teacher.last_name, "LOPEZ PEREZ")
        assignments = set(
            AsignacionDocente.objects.filter(docente=teacher).values_list(
                "materia_id", "curso_id"
            )
        )
        self.assertEqual(
            assignments,
            {
                (programming.pk, technical_course.pk),
                (office.pk, general_course.pk),
            },
        )
        self.assertEqual(summary["asignaciones"], 2)
        self.assertEqual(len(summary["claves_temporales"]), 1)
        self.assertEqual(len(summary["reporte"]), 1)
        self.assertEqual(summary["reporte"][0]["rol"], "Docente")
        self.assertEqual(summary["reporte"][0]["curso"], "2º INF A, 2º CIENCIAS B")

    def test_institutional_workbook_parses_all_sheets_and_course_metadata(self):
        existing_student = User.objects.create_user(
            username="0123456789",
            email="diego@example.com",
            password="OldStrongPass!234",
            identification="0123456789",
        )
        previous_course = Curso.objects.create(nombre="Curso anterior", codigo="ANT")
        previous_course.estudiantes.add(existing_student)

        workbook = Workbook()
        first_sheet = workbook.active
        first_sheet.title = "Inicial 1"
        first_sheet["A1"] = "Curso:"
        first_sheet["B1"] = "2º INF."
        first_sheet["A2"] = "Paralelo:"
        first_sheet["B2"] = "A"
        first_sheet["B10"] = "Nómina de estudiante"
        first_sheet["C10"] = "Cédula de estudiante"
        first_sheet["B11"] = "ALARCON MERELO DIEGO MATIAS"
        first_sheet["C11"] = 123456789

        second_sheet = workbook.create_sheet('3º CIENCIAS "A"')
        second_sheet["B10"] = "Nómina de estudiante"
        second_sheet["C10"] = "Cédula de estudiante"
        second_sheet["B11"] = "PEREZ LOPEZ ANA MARIA"
        second_sheet["C11"] = 987654321

        source = BytesIO()
        workbook.save(source)
        source.seek(0)
        summary = importar_nomina(source, "nomina_institucional.xlsx")

        existing_student.refresh_from_db()
        self.assertEqual(existing_student.username, "0123456789")
        self.assertEqual(existing_student.identification, "0123456789")
        self.assertEqual(existing_student.last_name, "ALARCON MERELO")
        self.assertEqual(existing_student.first_name, "DIEGO MATIAS")
        self.assertEqual(existing_student.email, "diego@example.com")
        self.assertEqual(
            list(existing_student.cursos.values_list("codigo", flat=True)),
            ["2-INF-A"],
        )

        second_student = User.objects.get(identification="0987654321")
        self.assertEqual(second_student.username, "0987654321")
        self.assertEqual(second_student.last_name, "PEREZ LOPEZ")
        self.assertEqual(second_student.first_name, "ANA MARIA")
        self.assertEqual(second_student.email, "estudiante-0987654321@nomina.invalid")
        self.assertTrue(
            Curso.objects.filter(
                nombre="3º BGU Ciencias A",
                estudiantes=second_student,
            ).exists()
        )
        self.assertEqual(summary["filas"], 2)

    def test_management_command_imports_excel_file(self):
        source = make_workbook(
            [["3001", "Mía", "Ruiz", "mia@example.com", "1A", "Primero A"]]
        )
        excel_file = NamedTemporaryFile(suffix=".xlsx", delete=False)
        try:
            excel_file.write(source.read())
            excel_file.close()
            output = StringIO()
            call_command("importar_nomina", excel_file.name, stdout=output)
        finally:
            if os.path.exists(excel_file.name):
                os.unlink(excel_file.name)

        self.assertTrue(User.objects.filter(identification="3001").exists())
        self.assertIn("Claves temporales", output.getvalue())

    def test_import_creates_student_and_moves_existing_student(self):
        student = User.objects.create_user(
            username="student-1",
            email="old@example.com",
            password="OldStrongPass!234",
            identification="1001",
        )
        previous_course = Curso.objects.create(nombre="Año anterior", codigo="OLD")
        previous_course.estudiantes.add(student)

        source = make_workbook(
            [["1001", "Ana", "Pérez", "ana@example.com", "2026A", "Curso 2026"]]
        )
        summary = importar_nomina(source, "nomina.xlsx")

        student.refresh_from_db()
        self.assertEqual(student.first_name, "Ana")
        self.assertEqual(student.last_name, "Pérez")
        self.assertEqual(student.email, "ana@example.com")
        self.assertTrue(student.debe_cambiar_password)
        self.assertEqual(list(student.cursos.values_list("codigo", flat=True)), ["2026A"])
        self.assertEqual(summary["estudiantes_actualizados"], 1)
        self.assertEqual(summary["cursos_creados"], 1)

        source = make_workbook(
            [["1002", "Luis", "Díaz", "luis@example.com", "2026A", "Curso 2026"]]
        )
        with patch("apps.usuarios.services.get_random_string", return_value="Temporary!234"):
            summary = importar_nomina(source, "nomina.xlsx")
        created_student = User.objects.get(identification="1002")
        self.assertEqual(created_student.rol, User.Role.STUDENT)
        self.assertTrue(created_student.debe_cambiar_password)
        self.assertNotEqual(created_student.password, "Temporary!234")
        self.assertTrue(check_password("Temporary!234", created_student.password))
        self.assertEqual(summary["claves_temporales"], [("1002", "Temporary!234")])

    def test_course_import_page_uses_shared_import_service(self):
        admin_user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="AdminStrongPass!234",
        )
        self.client.force_login(admin_user)
        source = make_workbook(
            [["2001", "Eva", "López", "eva@example.com", "2B", "Segundo B"]]
        )
        upload = SimpleUploadedFile(
            "nomina.xlsx",
            source.read(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        response = self.client.post(
            reverse("admin:evaluaciones_curso_importar_nomina"),
            {"archivo": upload},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Clave Temporal")
        self.assertContains(response, "López Eva")
        self.assertTrue(User.objects.filter(identification="2001").exists())
        self.assertTrue(
            Curso.objects.filter(
                codigo="2B", estudiantes__identification="2001"
            ).exists()
        )