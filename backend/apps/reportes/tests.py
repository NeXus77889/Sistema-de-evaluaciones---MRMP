import tempfile
from unittest.mock import ANY, patch

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reversefrom django.utils import timezone

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


class NearbyIpTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher2",
            email="teacher2@example.com",
            password="StrongPass!234",
            rol=User.Role.TEACHER,
        )
        materia = Materia.objects.create(nombre="Lengua", codigo="LEN")
        curso = Curso.objects.create(nombre="Cuarto", codigo="4A")
        AsignacionDocente.objects.create(docente=self.teacher, materia=materia, curso=curso)
        self.exam = Exam.objects.create(
            teacher=self.teacher,
            materia=materia,
            curso=curso,
            title="Lengua",
            duration_minutes=20,
            available_from=timezone.now(),
            detect_nearby_ips=True,
        )

    def make_attempt(self, username, ip):
        student = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="StrongPass!234",
            rol=User.Role.STUDENT,
            identification=f"ID-{username}",
        )
        return Attempt.objects.create(
            exam=self.exam,
            student=student,
            status=Attempt.Status.SUBMITTED,
            started_at=timezone.now(),
            submitted_at=timezone.now(),
            score=5,
            percentage=50,
            suspicion_score=0,
            suspicion_level="BAJO",
            ip_address=ip,
        )

    def test_finds_same_ip_and_same_network_but_not_other_networks(self):
        main = self.make_attempt("main", "190.10.20.5")
        same_ip = self.make_attempt("sameip", "190.10.20.5")
        same_net = self.make_attempt("samenet", "190.10.20.77")
        self.make_attempt("far", "190.10.21.5")
        self.make_attempt("noip", None)
        from apps.monitoreo.network import find_nearby_attempts

        found = {item.attempt.pk: item.relation for item in find_nearby_attempts(main)}
        self.assertEqual(found, {same_ip.pk: "Misma IP", same_net.pk: "Misma red"})

    def test_pdf_has_network_section_only_when_enabled_and_allowed(self):
        from apps.reportes.services import build_pdf

        main = self.make_attempt("main", "190.10.20.5")
        self.make_attempt("sameip", "190.10.20.5")
        with_network = build_pdf(main)
        self.assertTrue(with_network.startswith(b"%PDF"))
        without_network = build_pdf(main, include_network=False)
        self.assertGreater(len(with_network), len(without_network))

        self.exam.detect_nearby_ips = False
        self.exam.save()
        main.refresh_from_db()
        disabled = build_pdf(main, include_network=True)
        self.assertEqual(len(disabled), len(without_network))

    def test_student_download_hides_other_students(self):
        main = self.make_attempt("main", "190.10.20.5")
        self.make_attempt("sameip", "190.10.20.5")
        self.exam.results_visible = True
        self.exam.save()
        with patch("apps.reportes.services.build_pdf", return_value=b"%PDF-test") as build:
            self.client.force_login(main.student)
            self.client.get(reverse("report-download", args=[main.pk]))
            build.assert_called_once_with(ANY, include_network=False)

    def test_get_client_ip_counts_proxies_from_the_right(self):
        from django.test import RequestFactory

        from apps.monitoreo.network import get_client_ip

        request = RequestFactory().get(
            "/", HTTP_X_FORWARDED_FOR="6.6.6.6, 190.10.20.5, 10.0.0.1, 10.0.0.2", REMOTE_ADDR="10.0.0.3"
        )
        with override_settings(CLIENT_IP_PROXY_HOPS=3):
            self.assertEqual(get_client_ip(request), "190.10.20.5")
        bare = RequestFactory().get("/", REMOTE_ADDR="190.10.20.9")
        self.assertEqual(get_client_ip(bare), "190.10.20.9")
