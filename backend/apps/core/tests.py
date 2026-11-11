import json
from decimal import Decimal
from io import BytesIO

from django.contrib import admin as django_admin
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from docx import Document

from apps.evaluaciones.forms import ExamForm
from apps.evaluaciones.academic import course_sort_key, group_items_by_level
from apps.evaluaciones.models import AsignacionDocente, Curso, Exam, Materia, Option, Question
from apps.intentos.models import Attempt, Incident
from apps.core.models import TicketAtencion
from apps.usuarios.models import User


class AuthenticationAndAuthoringTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher",
            email="teacher@example.com",
            password="StrongPass!234",
            rol=User.Role.TEACHER,
            debe_cambiar_password=False,
        )
        self.student = User.objects.create_user(
            username="student",
            email="student@example.com",
            password="StrongPass!234",
            rol=User.Role.STUDENT,
            debe_cambiar_password=False,
        )
        self.materia = Materia.objects.create(nombre="Matemáticas", codigo="MAT")
        self.curso = Curso.objects.create(nombre="Primero", codigo="1A")
        self.curso.estudiantes.add(self.student)
        AsignacionDocente.objects.create(
            docente=self.teacher,
            materia=self.materia,
            curso=self.curso,
        )

    def test_academic_course_sort_places_levels_and_baccalaureate_specialties(self):
        names = [
            "2º BGU Informática",
            "5º A",
            "Inicial 2",
            "1º BGU Contabilidad",
            "8º A",
            "2º A",
            "1º BGU Ciencias",
            "Inicial 1",
            "1º A",
        ]
        courses = [
            Curso.objects.create(nombre=name, codigo=f"C{index}")
            for index, name in enumerate(names, start=1)
        ]

        ordered_names = [course.nombre for course in sorted(courses, key=course_sort_key)]

        self.assertEqual(
            ordered_names,
            [
                "Inicial 1",
                "Inicial 2",
                "1º A",
                "2º A",
                "5º A",
                "8º A",
                "1º BGU Ciencias",
                "1º BGU Contabilidad",
                "2º BGU Informática",
            ],
        )

    def test_multi_level_exam_is_listed_once(self):
        upper_course = Curso.objects.create(nombre="9º A", codigo="9A")
        exam = Exam.objects.create(
            teacher=self.teacher,
            materia=self.materia,
            curso=self.curso,
            title="Evaluación multcurso",
            duration_minutes=30,
            available_from=timezone.now(),
        )
        exam.cursos.add(upper_course)

        groups = group_items_by_level([exam])

        self.assertEqual(sum(len(group["items"]) for group in groups), 1)
        self.assertEqual(groups[0]["label"], "Básica Elemental")

    def test_admin_dashboard_groups_tickets_and_exposes_filters(self):
        administrator = User.objects.create_user(
            username="secretaria",
            email="secretaria@example.com",
            password="StrongPass!234",
            rol=User.Role.ADMINISTRATOR,
            is_staff=True,
            debe_cambiar_password=False,
        )
        ticket = TicketAtencion.objects.create(
            codigo="SEC-PASS-123456",
            tipo=TicketAtencion.Tipo.PASSWORD,
            estudiante=self.student,
        )
        exam = Exam.objects.create(
            teacher=self.teacher,
            materia=self.materia,
            curso=self.curso,
            title="Evaluación de auditoría",
            duration_minutes=30,
            available_from=timezone.now(),
        )
        second_course = Curso.objects.create(nombre="Segundo A", codigo="2A")
        second_course.estudiantes.add(self.student)
        exam.cursos.add(second_course)
        attempt = Attempt.objects.create(
            exam=exam,
            student=self.student,
            started_at=timezone.now(),
        )
        incident = Incident.objects.create(
            attempt=attempt,
            kind=Incident.Kind.TAB_HIDDEN,
            description="Pestaña no visible",
            severity=Incident.Severity.MEDIUM,
        )
        self.client.force_login(administrator)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(ticket.creado_en)
        self.assertIsNotNone(incident.occurred_at)
        self.assertContains(response, "Básica Elemental")
        self.assertContains(response, ticket.codigo)
        self.assertContains(response, f'data-course="{self.curso.pk}"')
        self.assertContains(response, "data-filter-student")
        self.assertContains(response, "data-filter-course")
        self.assertContains(response, "data-filter-from")
        self.assertContains(response, "data-filter-to")
        self.assertContains(response, "data-filter-month")
        self.assertNotContains(response, "data-filter-type")
        self.assertContains(response, incident.get_kind_display())

    def test_exam_admin_filters_courses_from_many_to_many_assignments(self):
        administrator = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="AdminStrongPass!234",
        )
        other_course = Curso.objects.create(nombre="Segundo EGB B", codigo="2EGBB")
        matching_exam = Exam.objects.create(
            teacher=self.teacher,
            materia=self.materia,
            curso=self.curso,
            title="Examen de curso secundario",
            duration_minutes=30,
            available_from=timezone.now(),
        )
        matching_exam.cursos.add(other_course)
        Exam.objects.create(
            teacher=self.teacher,
            materia=self.materia,
            curso=self.curso,
            title="Examen de otro paralelo",
            duration_minutes=30,
            available_from=timezone.now(),
        )
        self.client.force_login(administrator)

        response = self.client.get(
            reverse("admin:evaluaciones_exam_changelist"),
            {"curso_paralelo": other_course.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, matching_exam.title)
        self.assertNotContains(response, "Examen de otro paralelo")

    def test_login_and_dashboard_require_authentication(self):
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)
        self.assertTrue(self.client.login(username="teacher", password="StrongPass!234"))
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Espacio docente")

    def test_teacher_dashboard_groups_incidents_by_course_and_student(self):
        exam = Exam.objects.create(
            teacher=self.teacher,
            materia=self.materia,
            curso=self.curso,
            title="Evaluación monitoreada",
            duration_minutes=30,
            available_from=timezone.now(),
        )
        attempt = Attempt.objects.create(
            exam=exam,
            student=self.student,
            started_at=timezone.now(),
        )
        tab_incident = Incident.objects.create(
            attempt=attempt,
            kind=Incident.Kind.TAB_HIDDEN,
            description="Pestaña no visible",
            severity=Incident.Severity.MEDIUM,
        )
        device_incident = Incident.objects.create(
            attempt=attempt,
            kind=Incident.Kind.CAMERA_LOST,
            description="Cámara desconectada",
            severity=Incident.Severity.HIGH,
        )
        attempt.status = Attempt.Status.SUBMITTED
        attempt.submitted_at = timezone.now()
        attempt.save(update_fields=["status", "submitted_at"])
        ticket_code = f"SEC-PROCTOR-{attempt.pk}-{device_incident.pk}"
        TicketAtencion.objects.create(
            codigo=ticket_code,
            tipo=TicketAtencion.Tipo.PROCTOR,
            estudiante=self.student,
            intento=attempt,
        )
        self.client.force_login(self.teacher)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="incident-course-group"')
        self.assertContains(response, 'class="incident-student-group"')
        self.assertContains(response, "<strong>student</strong>")
        self.assertContains(response, ">2</b> faltas")
        self.assertContains(response, tab_incident.get_kind_display())
        self.assertContains(response, device_incident.get_kind_display())
        self.assertContains(response, ticket_code)
        self.assertContains(response, "Pendiente")
        self.assertContains(response, "data-filter-from")
        self.assertContains(response, "data-filter-to")
        self.assertContains(response, "data-filter-month")
        incident_groups = response.context["incidence_groups"]
        self.assertEqual(len(incident_groups), 1)
        self.assertEqual(
            sum(
                len(student_group["incidents"])
                for course_group in incident_groups
                for student_group in course_group["students"]
            ),
            2,
        )

    def test_temporary_password_requires_change_before_dashboard(self):
        self.student.debe_cambiar_password = True
        self.student.save(update_fields=["debe_cambiar_password"])
        self.client.force_login(self.student)

        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, reverse("password-change"))
        self.assertEqual(self.client.get(reverse("password-change")).status_code, 200)
        response = self.client.post(
            reverse("password-change"),
            {
                "old_password": "StrongPass!234",
                "new_password1": "DifferentStrong!5678",
                "new_password2": "DifferentStrong!5678",
            },
        )

        self.assertRedirects(response, reverse("dashboard"))
        self.student.refresh_from_db()
        self.assertFalse(self.student.debe_cambiar_password)
        self.assertTrue(self.student.check_password("DifferentStrong!5678"))

    def test_password_gate_allows_ticket_creation(self):
        self.student.debe_cambiar_password = True
        self.student.save(update_fields=["debe_cambiar_password"])
        self.client.force_login(self.student)

        response = self.client.post(
            reverse("create-support-ticket"),
            data=json.dumps(
                {
                    "tipo": "PASS",
                    "codigo": "SEC-PASS-739182",
                    "correo": self.student.email,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        duplicate_response = self.client.post(
            reverse("create-support-ticket"),
            data=json.dumps(
                {
                    "tipo": "PASS",
                    "codigo": "SEC-PASS-739182",
                    "correo": self.student.email,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(duplicate_response.status_code, 200)
        self.assertEqual(duplicate_response.json()["ticket_id"], response.json()["ticket_id"])
        self.assertEqual(TicketAtencion.objects.filter(codigo="SEC-PASS-739182").count(), 1)

    def test_ticket_api_rejects_non_string_type(self):
        response = self.client.post(
            reverse("create-support-ticket"),
            data=json.dumps({"tipo": ["PASS"], "codigo": "SEC-PASS-123456"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_password_ticket_resets_student_password_and_records_secretary(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("create-support-ticket"),
            data=json.dumps(
                {
                    "tipo": "PASS",
                    "codigo": "SEC-PASS-123456",
                    "correo": self.student.email,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        ticket = TicketAtencion.objects.get(codigo="SEC-PASS-123456")
        self.assertEqual(ticket.estado, TicketAtencion.Estado.PENDIENTE)

        secretary = User.objects.create_superuser(
            username="secretary",
            email="secretary@example.com",
            password="SecretaryStrong!234",
        )
        self.client.force_login(secretary)
        response = self.client.post(
            reverse("ticket-attention"), {"codigo": ticket.codigo}
        )
        self.assertRedirects(response, reverse("ticket-password", args=[ticket.pk]))
        response = self.client.post(
            reverse("ticket-password", args=[ticket.pk]),
            {
                "new_password1": "TemporaryReset!9876",
                "new_password2": "TemporaryReset!9876",
            },
        )

        self.assertRedirects(response, reverse("dashboard"))
        ticket.refresh_from_db()
        self.student.refresh_from_db()
        self.assertEqual(ticket.estado, TicketAtencion.Estado.RESUELTO)
        self.assertEqual(ticket.atendido_por, secretary)
        self.assertIsNotNone(ticket.atendido_en)
        self.assertTrue(self.student.check_password("TemporaryReset!9876"))
        self.assertTrue(self.student.debe_cambiar_password)

    def test_attention_prefers_pending_ticket_when_code_was_resolved_before(self):
        TicketAtencion.objects.create(
            codigo="SEC-PASS-123456",
            tipo=TicketAtencion.Tipo.PASSWORD,
            estado=TicketAtencion.Estado.RESUELTO,
            estudiante=self.student,
        )
        pending_ticket = TicketAtencion.objects.create(
            codigo="SEC-PASS-123456",
            tipo=TicketAtencion.Tipo.PASSWORD,
            estudiante=self.student,
        )
        secretary = User.objects.create_superuser(
            username="secretary",
            email="secretary@example.com",
            password="SecretaryStrong!234",
        )
        self.client.force_login(secretary)

        response = self.client.post(
            reverse("ticket-attention"), {"codigo": "SEC-PASS-123456"}
        )

        self.assertRedirects(
            response,
            reverse("ticket-password", args=[pending_ticket.pk]),
        )

    def test_user_lookup_ticket_shows_account_and_resolves(self):
        response = self.client.post(
            reverse("create-support-ticket"),
            data=json.dumps(
                {
                    "tipo": "USER",
                    "codigo": "SEC-USER-739182",
                    "correo": self.student.email,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        ticket = TicketAtencion.objects.get(codigo="SEC-USER-739182")
        secretary = User.objects.create_superuser(
            username="secretary",
            email="secretary@example.com",
            password="SecretaryStrong!234",
        )
        self.client.force_login(secretary)

        response = self.client.post(
            reverse("ticket-attention"), {"codigo": ticket.codigo}
        )
        self.assertRedirects(response, reverse("ticket-user-info", args=[ticket.pk]))
        response = self.client.get(reverse("ticket-user-info", args=[ticket.pk]))
        self.assertContains(response, self.student.identification or self.student.username)
        self.assertContains(response, self.student.email)
        self.client.post(reverse("ticket-user-info", args=[ticket.pk]))

        ticket.refresh_from_db()
        self.assertEqual(ticket.estado, TicketAtencion.Estado.RESUELTO)
        self.assertEqual(ticket.atendido_por, secretary)

    def test_exam_ticket_redirects_to_the_student_attempt(self):
        self.student.identification = "0966504938"
        self.student.save(update_fields=["identification"])
        exam = Exam.objects.create(
            teacher=self.teacher,
            materia=self.materia,
            curso=self.curso,
            title="Examen reclamado",
            duration_minutes=30,
            available_from=timezone.now(),
        )
        attempt = Attempt.objects.create(
            exam=exam,
            student=self.student,
            status=Attempt.Status.SUBMITTED,
            started_at=timezone.now(),
            submitted_at=timezone.now(),
            score=8,
            percentage=80,
        )
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("create-support-ticket"),
            data=json.dumps(
                {
                    "tipo": "EXAM",
                    "codigo": f"SEC-EXAM-{exam.pk}-0966504938",
                    "identificacion": "0966504938",
                    "intento_id": attempt.pk,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        ticket = TicketAtencion.objects.get(codigo=f"SEC-EXAM-{exam.pk}-0966504938")
        secretary = User.objects.create_superuser(
            username="secretary",
            email="secretary@example.com",
            password="SecretaryStrong!234",
        )
        self.client.force_login(secretary)
        response = self.client.post(
            reverse("ticket-attention"), {"codigo": ticket.codigo}
        )

        self.assertRedirects(
            response,
            reverse("admin:intentos_attempt_change", args=[attempt.pk]),
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.intento, attempt)
        self.assertEqual(ticket.estado, TicketAtencion.Estado.PENDIENTE)

    def test_proctor_ticket_redirects_secretary_to_attempt(self):
        exam = Exam.objects.create(
            teacher=self.teacher,
            materia=self.materia,
            curso=self.curso,
            title="Examen con incidencia",
            duration_minutes=30,
            available_from=timezone.now(),
        )
        attempt = Attempt.objects.create(
            exam=exam,
            student=self.student,
            started_at=timezone.now(),
        )
        ticket = TicketAtencion.objects.create(
            codigo=f"SEC-PROCTOR-{attempt.pk}-1",
            tipo=TicketAtencion.Tipo.PROCTOR,
            estudiante=self.student,
            intento=attempt,
        )
        secretary = User.objects.create_superuser(
            username="secretary",
            email="secretary@example.com",
            password="SecretaryStrong!234",
        )
        self.client.force_login(secretary)

        response = self.client.post(
            reverse("ticket-attention"), {"codigo": ticket.codigo}
        )

        self.assertRedirects(
            response,
            reverse("admin:intentos_attempt_change", args=[attempt.pk]),
        )

        attempt.score = Decimal("9.00")
        attempt.percentage = Decimal("90.00")
        admin_request = RequestFactory().post("/")
        admin_request.user = secretary
        django_admin.site._registry[Attempt].save_model(
            admin_request, attempt, form=None, change=True
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.estado, TicketAtencion.Estado.RESUELTO)
        self.assertEqual(ticket.atendido_por, secretary)
        self.assertIsNotNone(ticket.atendido_en)

    def test_teacher_can_create_exam_and_question(self):
        self.client.login(username="teacher", password="StrongPass!234")
        response = self.client.post(
            reverse("exam-create"),
            {
                "title": "Evaluación de prueba",
                "materia": self.materia.pk,
                "curso": self.curso.pk,
                "description": "Descripción",
                "duration_minutes": 30,
                "available_from": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                "available_until": "",
                "published": "on",
                "results_visible": "",
                "students": [self.student.pk],
                "questions_json": json.dumps([
                    {
                        "text": "¿Cuánto es 2 + 2?",
                        "points": "2",
                        "options": [
                            {"text": "4", "correct": True},
                            {"text": "5", "correct": False},
                        ],
                    }
                ]),
            },
        )
        self.assertRedirects(response, reverse("dashboard"))
        exam = Exam.objects.get(title="Evaluación de prueba")
        self.assertEqual(exam.teacher, self.teacher)
        self.assertEqual(list(exam.students.all()), [self.student])
        question = Question.objects.get(exam=exam)
        self.assertEqual(question.options.filter(is_correct=True).count(), 1)

    def test_teacher_can_preview_questions_from_docx(self):
        document = Document()
        document.add_paragraph("1. ¿Cuál es la respuesta correcta?")
        document.add_paragraph("A) Alternativa uno")
        document.add_paragraph("B) [x] Alternativa dos")
        document.add_paragraph("2. Segunda pregunta")
        document.add_paragraph("A. Opción A")
        document.add_paragraph("B. Opción B")
        content = BytesIO()
        document.save(content)
        upload = SimpleUploadedFile(
            "preguntas.docx",
            content.getvalue(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse("exam-import-preview"), {"archivo": upload}
        )

        self.assertEqual(response.status_code, 200)
        questions = response.json()["questions"]
        self.assertEqual(len(questions), 2)
        self.assertEqual(questions[0]["text"], "¿Cuál es la respuesta correcta?")
        self.assertEqual(
            [option["correct"] for option in questions[0]["options"]],
            [False, True],
        )
        self.assertEqual(
            [option["correct"] for option in questions[1]["options"]],
            [False, False],
        )

    def test_teacher_form_excludes_students_outside_selected_course(self):
        other_student = User.objects.create_user(
            username="other-student",
            email="other-student@example.com",
            password="StrongPass!234",
            rol=User.Role.STUDENT,
            debe_cambiar_password=False,
        )
        other_course = Curso.objects.create(nombre="Segundo", codigo="2A")
        other_course.estudiantes.add(other_student)
        form = ExamForm({"curso": self.curso.pk}, docente=self.teacher)

        self.assertQuerySetEqual(
            form.fields["students"].queryset,
            [self.student],
        )

    def test_teacher_exam_form_supports_assigned_extra_courses(self):
        extra_course = Curso.objects.create(nombre="Primero B", codigo="1B")
        unassigned_course = Curso.objects.create(nombre="Segundo A", codigo="2A")
        extra_student = User.objects.create_user(
            username="extra-student",
            email="extra-student@example.com",
            password="StrongPass!234",
            rol=User.Role.STUDENT,
        )
        extra_course.estudiantes.add(extra_student)
        AsignacionDocente.objects.create(
            docente=self.teacher,
            materia=self.materia,
            curso=extra_course,
        )

        form = ExamForm(
            {
                "materia": self.materia.pk,
                "curso": self.curso.pk,
                "cursos": [extra_course.pk],
            },
            docente=self.teacher,
        )
        unassigned_form = ExamForm(
            {
                "materia": self.materia.pk,
                "curso": self.curso.pk,
                "cursos": [unassigned_course.pk],
            },
            docente=self.teacher,
        )

        self.assertQuerySetEqual(
            form.fields["cursos"].queryset,
            [self.curso, extra_course],
        )
        self.assertQuerySetEqual(
            form.fields["students"].queryset,
            [self.student, extra_student],
            ordered=False,
        )
        form.is_valid()
        unassigned_form.is_valid()
        self.assertNotIn("cursos", form.errors)
        self.assertIn("cursos", unassigned_form.errors)

    def test_exam_form_persists_all_selected_destination_courses(self):
        second_course = Curso.objects.create(nombre="2º Ciencias", codigo="2C")
        AsignacionDocente.objects.create(
            docente=self.teacher,
            materia=self.materia,
            curso=second_course,
        )
        form = ExamForm(
            {
                "materia": self.materia.pk,
                "cursos": [self.curso.pk, second_course.pk],
                "title": "Evaluación en varios cursos",
                "duration_minutes": 30,
                "available_from": "2030-01-01T10:00",
            },
            docente=self.teacher,
        )

        self.assertTrue(form.is_valid(), form.errors)
        exam = form.save(commit=False)
        exam.teacher = self.teacher
        exam.save()
        form.save_m2m()

        self.assertSetEqual(
            set(exam.cursos.all()),
            {self.curso, second_course},
        )

    def test_teacher_without_assignments_sees_secretariat_notice(self):
        unassigned_teacher = User.objects.create_user(
            username="unassigned-teacher",
            email="unassigned@example.com",
            password="StrongPass!234",
            rol=User.Role.TEACHER,
        )

        form = ExamForm(docente=unassigned_teacher)

        self.assertIn("Solicita a Secretaría", form.assignment_notice)
        self.assertFalse(form.fields["materia"].queryset.exists())
        self.assertFalse(form.fields["curso"].queryset.exists())

    def test_administrator_form_lists_all_courses_and_subjects(self):
        other_materia = Materia.objects.create(nombre="Ciencias", codigo="CIE")
        other_course = Curso.objects.create(nombre="Segundo", codigo="2A")
        administrator = User.objects.create_superuser(
            username="administrator",
            email="administrator@example.com",
            password="StrongPass!234",
        )

        form = ExamForm(
            {"materia": other_materia.pk, "curso": other_course.pk},
            docente=administrator,
        )

        self.assertQuerySetEqual(
            form.fields["materia"].queryset,
            Materia.objects.all(),
        )
        self.assertQuerySetEqual(
            form.fields["curso"].queryset,
            Curso.objects.all(),
        )
        form.is_valid()
        self.assertNotIn("curso", form.errors)

    def test_teacher_form_rejects_unassigned_subject_course_pair(self):
        other_materia = Materia.objects.create(nombre="Ciencias", codigo="CIE")
        other_course = Curso.objects.create(nombre="Segundo", codigo="2A")
        AsignacionDocente.objects.create(
            docente=self.teacher,
            materia=other_materia,
            curso=other_course,
        )

        form = ExamForm(
            {"materia": self.materia.pk, "curso": other_course.pk},
            docente=self.teacher,
        )

        self.assertFalse(form.is_valid())
        self.assertIn(
            "No tienes asignada esa materia en el curso seleccionado.",
            form.errors["curso"],
        )

    def test_student_cannot_open_teacher_result_page(self):
        exam = Exam.objects.create(
            teacher=self.teacher,
            materia=self.materia,
            curso=self.curso,
            title="Privada",
            duration_minutes=30,
            available_from=timezone.now(),
        )
        self.client.login(username="student", password="StrongPass!234")
        response = self.client.get(reverse("exam-results", args=[exam.pk]))
        self.assertEqual(response.status_code, 404)

    def test_student_dashboard_shows_published_exams_for_enrolled_course(self):
        available_exam = Exam.objects.create(
            teacher=self.teacher,
            materia=self.materia,
            curso=self.curso,
            title="Examen disponible por curso",
            duration_minutes=30,
            available_from=timezone.now(),
            published=True,
        )
        other_course = Curso.objects.create(nombre="Tercero", codigo="3A")
        AsignacionDocente.objects.create(
            docente=self.teacher,
            materia=self.materia,
            curso=other_course,
        )
        unavailable_exam = Exam.objects.create(
            teacher=self.teacher,
            materia=self.materia,
            curso=other_course,
            title="Examen de otro curso",
            duration_minutes=30,
            available_from=timezone.now(),
            published=True,
        )
        self.client.force_login(self.student)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, available_exam.title)
        self.assertNotContains(response, unavailable_exam.title)

        launch_response = self.client.get(
            reverse("exam-launch", args=[available_exam.pk])
        )
        self.assertEqual(launch_response.status_code, 200)
        self.assertContains(launch_response, 'id="preflight"')

        mismatch_response = self.client.get(
            reverse("exam-launch", args=[unavailable_exam.pk])
        )
        self.assertEqual(mismatch_response.status_code, 200)
        self.assertContains(mismatch_response, "no está asignada a tu curso")
        self.assertNotContains(mismatch_response, 'id="preflight"')

    def test_student_can_launch_exam_for_any_many_to_many_course(self):
        other_course = Curso.objects.create(nombre="Cuarto", codigo="4A")
        other_course.estudiantes.add(self.student)
        exam = Exam.objects.create(
            teacher=self.teacher,
            materia=self.materia,
            curso=self.curso,
            title="Examen multi-curso",
            duration_minutes=30,
            available_from=timezone.now(),
            published=True,
        )
        exam.cursos.add(other_course)
        self.client.force_login(self.student)

        response = self.client.get(reverse("exam-launch", args=[exam.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="preflight"')

    def test_exam_rejects_inactive_teacher_assignment(self):
        assignment = AsignacionDocente.objects.get(
            docente=self.teacher,
            materia=self.materia,
            curso=self.curso,
        )
        assignment.activo = False
        assignment.save(update_fields=["activo"])
        exam = Exam(
            teacher=self.teacher,
            materia=self.materia,
            curso=self.curso,
            title="Sin asignación activa",
            duration_minutes=30,
            available_from=timezone.now(),
        )

        with self.assertRaises(ValidationError):
            exam.save()

    def test_proctor_ticket_creation_via_api(self):
        exam = Exam.objects.create(
            teacher=self.teacher,
            materia=self.materia,
            curso=self.curso,
            title="Examen proctoring API",
            duration_minutes=30,
            available_from=timezone.now(),
        )
        attempt = Attempt.objects.create(
            exam=exam,
            student=self.student,
            started_at=timezone.now(),
        )
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("create-support-ticket"),
            data=json.dumps(
                {
                    "tipo": "PROCTOR",
                    "codigo": f"SEC-PROCTOR-{attempt.pk}-99",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        ticket = TicketAtencion.objects.get(codigo=f"SEC-PROCTOR-{attempt.pk}-99")
        self.assertEqual(ticket.tipo, TicketAtencion.Tipo.PROCTOR)
        self.assertEqual(ticket.intento, attempt)

    def test_report_download_generates_pdf_on_demand_when_missing(self):
        import tempfile
        from django.test import override_settings

        exam = Exam.objects.create(
            teacher=self.teacher,
            materia=self.materia,
            curso=self.curso,
            title="Examen sin PDF previo",
            duration_minutes=30,
            available_from=timezone.now(),
        )
        attempt = Attempt.objects.create(
            exam=exam,
            student=self.student,
            status=Attempt.Status.SUBMITTED,
            started_at=timezone.now(),
            submitted_at=timezone.now(),
            score=9,
            percentage=90,
        )
        self.client.force_login(self.teacher)
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.get(reverse("report-download", args=[attempt.pk]))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "application/pdf")
                attempt.refresh_from_db()
                self.assertTrue(hasattr(attempt, "report"))
                self.assertTrue(bool(attempt.report.pdf))
