import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.evaluaciones.models import AsignacionDocente, Curso, Exam, Materia, Option, Question
from apps.intentos.models import Answer, Attempt, Incident
from apps.intentos.services import finish_attempt
from apps.monitoreo.services import assess_attempt
from apps.core.models import TicketAtencion
from apps.usuarios.models import User


class AttemptApiTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher",
            email="teacher@example.com",
            password="StrongPass!234",
            rol=User.Role.TEACHER,
        )
        self.student = User.objects.create_user(
            username="student",
            email="student@example.com",
            password="StrongPass!234",
            rol=User.Role.STUDENT,
            identification="ST-001",
        )
        self.other_student = User.objects.create_user(
            username="other",
            email="other@example.com",
            password="StrongPass!234",
            rol=User.Role.STUDENT,
        )
        self.materia = Materia.objects.create(nombre="Ciencias", codigo="CIE")
        self.curso = Curso.objects.create(nombre="Segundo", codigo="2A")
        AsignacionDocente.objects.create(
            docente=self.teacher,
            materia=self.materia,
            curso=self.curso,
        )
        self.exam = Exam.objects.create(
            teacher=self.teacher,
            materia=self.materia,
            curso=self.curso,
            title="Ciencias",
            duration_minutes=30,
            available_from=timezone.now() - timedelta(minutes=1),
            published=True,
        )
        self.exam.students.add(self.student)
        self.question = Question.objects.create(exam=self.exam, text="Pregunta 1", points=2, position=1)
        self.correct = Option.objects.create(question=self.question, text="Correcta", is_correct=True, position=1)
        Option.objects.create(question=self.question, text="Incorrecta", is_correct=False, position=2)
        self.unanswered = Question.objects.create(exam=self.exam, text="Pregunta 2", points=3, position=2)
        Option.objects.create(question=self.unanswered, text="A", is_correct=True, position=1)
        Option.objects.create(question=self.unanswered, text="B", is_correct=False, position=2)
        self.client = APIClient()
        self.client.force_authenticate(self.student)

    def start_attempt(self):
        response = self.client.post(reverse("attempt-start", args=[self.exam.pk]))
        self.assertEqual(response.status_code, 201)
        return response.data["attempt_id"]

    def test_start_records_ip_only_when_exam_enables_detection(self):
        headers = {"HTTP_X_FORWARDED_FOR": "190.10.20.5", "REMOTE_ADDR": "10.0.0.1"}
        with self.settings(CLIENT_IP_PROXY_HOPS=1):
            attempt_id = self.client.post(
                reverse("attempt-start", args=[self.exam.pk]), **headers
            ).data["attempt_id"]
        self.assertIsNone(Attempt.objects.get(pk=attempt_id).ip_address)

        Attempt.objects.all().delete()
        self.exam.detect_nearby_ips = True
        self.exam.save()
        with self.settings(CLIENT_IP_PROXY_HOPS=1):
            attempt_id = self.client.post(
                reverse("attempt-start", args=[self.exam.pk]), **headers
            ).data["attempt_id"]
        self.assertEqual(Attempt.objects.get(pk=attempt_id).ip_address, "190.10.20.5")

    def test_start_hides_correct_answer_and_other_student_cannot_read_attempt(self):
        attempt_id = self.start_attempt()
        response = self.client.get(reverse("attempt-state", args=[attempt_id]))
        self.assertEqual(response.status_code, 200)
        question_data = response.data["questions"][0]
        self.assertNotIn("is_correct", question_data["options"][0])
        self.client.force_authenticate(self.other_student)
        self.assertEqual(self.client.get(reverse("attempt-state", args=[attempt_id])).status_code, 404)

    def test_answer_is_saved_and_grade_uses_all_question_points(self):
        attempt_id = self.start_attempt()
        response = self.client.post(
            reverse("attempt-answer", args=[attempt_id]),
            {"question_id": self.question.pk, "option_id": self.correct.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Answer.objects.count(), 1)
        attempt, changed = finish_attempt(attempt_id)
        self.assertTrue(changed)
        self.assertEqual(attempt.score, 2)
        self.assertEqual(attempt.percentage, 50)
        self.assertFalse(finish_attempt(attempt_id)[1])

    def test_student_cannot_start_unassigned_exam(self):
        self.exam.students.remove(self.student)
        self.curso.estudiantes.remove(self.student)
        response = self.client.post(reverse("attempt-start", args=[self.exam.pk]))
        self.assertEqual(response.status_code, 403)

    def test_student_can_start_exam_assigned_to_enrolled_course(self):
        self.exam.students.remove(self.student)
        self.curso.estudiantes.add(self.student)

        response = self.client.post(reverse("attempt-start", args=[self.exam.pk]))

        self.assertEqual(response.status_code, 201)

    def test_incident_is_idempotent_and_suspicion_is_bounded(self):
        attempt_id = self.start_attempt()
        event_id = str(uuid.uuid4())
        payload = {"kind": Incident.Kind.TAB_HIDDEN, "client_event_id": event_id, "duration_ms": 60000}
        first = self.client.post(reverse("attempt-incident", args=[attempt_id]), payload, format="json")
        second = self.client.post(reverse("attempt-incident", args=[attempt_id]), payload, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.data["duplicate"])
        self.assertEqual(first.data["focus_offense_count"], 1)
        self.assertTrue(second.data["duplicate"])
        attempt = Attempt.objects.get(pk=attempt_id)
        assessment = assess_attempt(attempt)
        self.assertEqual(assessment.incident_count, 1)
        self.assertEqual(assessment.score, 14)
        self.assertEqual(assessment.level, "BAJO")

    def test_incident_count_endpoint_returns_live_count_only_to_attempt_owner(self):
        attempt_id = self.start_attempt()
        count_url = reverse("attempt-incident-count", args=[attempt_id])
        self.assertEqual(self.client.get(count_url).data["incident_count"], 0)
        self.client.post(
            reverse("attempt-incident", args=[attempt_id]),
            {"kind": Incident.Kind.TAB_HIDDEN, "client_event_id": str(uuid.uuid4())},
            format="json",
        )
        response = self.client.get(count_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["incident_count"], 1)
        self.assertEqual(response.data["incident_limit"], 3)
        self.client.force_authenticate(self.other_student)
        self.assertEqual(self.client.get(count_url).status_code, 404)

    def test_non_device_incident_also_creates_a_visible_support_ticket(self):
        attempt_id = self.start_attempt()
        response = self.client.post(
            reverse("attempt-incident", args=[attempt_id]),
            {"kind": Incident.Kind.FULLSCREEN_EXIT, "client_event_id": str(uuid.uuid4())},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["security_ticket_code"])
        ticket = TicketAtencion.objects.get(codigo=response.data["security_ticket_code"])
        self.assertEqual(ticket.tipo, TicketAtencion.Tipo.PROCTOR)

    def test_device_incident_creates_idempotent_proctor_ticket(self):
        attempt_id = self.start_attempt()
        event_id = str(uuid.uuid4())
        payload = {
            "kind": Incident.Kind.CAMERA_LOST,
            "client_event_id": event_id,
        }

        first = self.client.post(
            reverse("attempt-incident", args=[attempt_id]), payload, format="json"
        )
        second = self.client.post(
            reverse("attempt-incident", args=[attempt_id]), payload, format="json"
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["security_ticket_code"], second.data["security_ticket_code"])
        ticket = TicketAtencion.objects.get(codigo=first.data["security_ticket_code"])
        self.assertEqual(ticket.tipo, TicketAtencion.Tipo.PROCTOR)
        self.assertEqual(ticket.intento_id, attempt_id)
        self.assertEqual(ticket.estudiante, self.student)
        self.assertEqual(TicketAtencion.objects.filter(tipo=TicketAtencion.Tipo.PROCTOR).count(), 1)
        self.assertFalse(first.data["auto_submitted"])
        self.assertEqual(
            Attempt.objects.get(pk=attempt_id).status,
            Attempt.Status.IN_PROGRESS,
        )

    @patch("apps.intentos.views.create_report_safely")
    def test_device_loss_counts_toward_three_incident_limit(self, create_report):
        attempt_id = self.start_attempt()

        response = self.client.post(
            reverse("attempt-incident", args=[attempt_id]),
            {"kind": Incident.Kind.MICROPHONE_MUTED, "client_event_id": str(uuid.uuid4())},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["auto_submitted"])
        self.assertEqual(Attempt.objects.get(pk=attempt_id).status, Attempt.Status.IN_PROGRESS)
        self.assertEqual(TicketAtencion.objects.filter(tipo=TicketAtencion.Tipo.PROCTOR).count(), 1)
        for kind in [Incident.Kind.TAB_HIDDEN, Incident.Kind.FULLSCREEN_EXIT]:
            response = self.client.post(
                reverse("attempt-incident", args=[attempt_id]),
                {"kind": kind, "client_event_id": str(uuid.uuid4())},
                format="json",
            )
        attempt = Attempt.objects.get(pk=attempt_id)
        self.assertTrue(response.data["auto_submitted"])
        self.assertEqual(attempt.status, Attempt.Status.SUBMITTED)
        create_report.assert_called_once_with(attempt)

    def test_fullscreen_exit_uses_same_three_incident_limit(self):
        attempt_id = self.start_attempt()
        for number in range(3):
            response = self.client.post(
                reverse("attempt-incident", args=[attempt_id]),
                {"kind": Incident.Kind.FULLSCREEN_EXIT, "client_event_id": str(uuid.uuid4())},
                format="json",
            )
            self.assertEqual(response.data["incident_count"], number + 1)
        self.assertTrue(response.data["auto_submitted"])

    @patch("apps.intentos.views.create_report_safely")
    def test_third_focus_offense_submits_the_attempt(self, create_report):
        attempt_id = self.start_attempt()
        kinds = [
            Incident.Kind.TAB_HIDDEN,
            Incident.Kind.WINDOW_BLUR,
            Incident.Kind.TAB_HIDDEN,
        ]

        for offense_number, kind in enumerate(kinds, start=1):
            response = self.client.post(
                reverse("attempt-incident", args=[attempt_id]),
                {"kind": kind, "client_event_id": str(uuid.uuid4())},
                format="json",
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["focus_offense_count"], offense_number)
            self.assertEqual(response.data["auto_submitted"], offense_number == 3)

        attempt = Attempt.objects.get(pk=attempt_id)
        self.assertEqual(attempt.status, Attempt.Status.SUBMITTED)
        create_report.assert_called_once_with(attempt)
