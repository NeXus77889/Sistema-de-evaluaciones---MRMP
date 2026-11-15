import tempfile

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.evaluaciones.models import AsignacionDocente, Curso, Exam, Materia
from apps.intentos.models import Attempt
from apps.reportes.models import AttemptReport
from apps.reportes.services import create_and_email_report
from apps.usuarios.models import User


class AttemptReportTests(TestCase):
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
        materia = Materia.objects.create(nombre="Historia", codigo="HIS")
        curso = Curso.objects.create(nombre="Tercero", codigo="3A")
        AsignacionDocente.objects.create(docente=self.teacher, materia=materia, curso=curso)
        self.exam = Exam.objects.create(
            teacher=self.teacher,
            materia=materia,
            curso=curso,
            title="Historia",
            duration_minutes=20,
            available_from=timezone.now(),
        )
        self.attempt = Attempt.objects.create(
            exam=self.exam,
            student=self.student,
            status=Attempt.Status.SUBMITTED,
            started_at=timezone.now(),
            submitted_at=timezone.now(),
            score=8,
            percentage=80,
            suspicion_score=12,
            suspicion_level="BAJO",
        )

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_pdf_is_generated_and_email_is_sent_once(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                report = create_and_email_report(self.attempt.pk)
                self.assertTrue(report.pdf.name.startswith("private/reports/"))
                with report.pdf.open("rb") as pdf:
                    self.assertTrue(pdf.read().startswith(b"%PDF"))
                self.assertEqual(len(mail.outbox), 1)
                self.assertEqual(mail.outbox[0].to, [self.teacher.email])
                self.assertEqual(mail.outbox[0].attachments[0][2], "application/pdf")
                create_and_email_report(self.attempt.pk)
                self.assertEqual(len(mail.outbox), 1)
                self.assertEqual(AttemptReport.objects.count(), 1)
