from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.intentos.models import Attempt
from apps.monitoreo.services import assess_attempt
from apps.reportes.models import AttemptReport


def build_pdf(attempt):
    assessment = assess_attempt(attempt)
    events = list(attempt.incidents.all())
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=22 * mm,
        bottomMargin=20 * mm,
        title=f"Informe de {attempt.exam.title}",
        author="Sistema de evaluaciones",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], textColor=colors.HexColor("#173b35"), alignment=TA_LEFT, fontSize=20, leading=24, spaceAfter=8))
    styles.add(ParagraphStyle(name="SmallCell", parent=styles["BodyText"], fontSize=8, leading=10))
    styles.add(ParagraphStyle(name="SectionHeading", parent=styles["Heading2"], textColor=colors.HexColor("#173b35"), fontSize=12, leading=15, spaceBefore=12, spaceAfter=6))

    def page_footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d4ddd9"))
        canvas.line(18 * mm, 15 * mm, A4[0] - 18 * mm, 15 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#566660"))
        canvas.drawString(18 * mm, 10 * mm, "Informe confidencial de evaluación")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Página {doc.page}")
        canvas.restoreState()

    teacher_name = attempt.exam.teacher.get_full_name() or attempt.exam.teacher.username
    student_name = attempt.student.get_full_name() or attempt.student.username
    started = timezone.localtime(attempt.started_at).strftime("%d/%m/%Y %H:%M:%S")
    submitted = timezone.localtime(attempt.submitted_at).strftime("%d/%m/%Y %H:%M:%S") if attempt.submitted_at else "En curso"
    summary = (
        f"Se registraron {assessment.incident_count} incidencias. "
        f"El nivel calculado es {assessment.level} ({assessment.score}/100). "
        "Este indicador describe señales observadas por el navegador; no demuestra plagio "
        "ni modifica la calificación académica. La revisión docente debe considerar el contexto."
    )
    story = [
        Paragraph("Informe de intento", styles["ReportTitle"]),
        Paragraph(attempt.exam.title, styles["Heading2"]),
        Spacer(1, 5 * mm),
    ]
    details = [
        ["Estudiante", student_name, "Identificación", attempt.student.identification or "No registrada"],
        ["Docente", teacher_name, "Evaluación", attempt.exam.title],
        ["Inicio", started, "Finalización", submitted],
        ["Calificación", str(attempt.score), "Respuestas correctas", f"{attempt.percentage}%"],
        ["Nivel de sospecha", assessment.level, "Puntuación", f"{assessment.score}/100"],
    ]
    details_table = Table(details, colWidths=[30 * mm, 58 * mm, 30 * mm, 58 * mm])
    details_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#edf3f0")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#edf3f0")),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#173b35")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#173b35")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d4ddd9")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([details_table, Paragraph("Análisis", styles["SectionHeading"]), Paragraph(summary, styles["BodyText"])])
    by_kind = ", ".join(
        f"{Incident_label(kind)}: {count}" for kind, count in sorted(assessment.by_kind.items())
    ) or "Sin incidencias registradas."
    story.extend([Paragraph("Conteo por tipo", styles["SectionHeading"]), Paragraph(by_kind, styles["BodyText"])])
    story.append(Paragraph("Cronología de incidencias", styles["SectionHeading"]))
    rows = [["Fecha y hora", "Tipo", "Duración", "Gravedad", "Descripción"]]
    for event in events:
        occurred = timezone.localtime(event.occurred_at).strftime("%d/%m/%Y %H:%M:%S")
        duration = f"{event.duration_ms / 1000:.1f} s" if event.duration_ms is not None else "No disponible"
        rows.append([
            Paragraph(occurred, styles["SmallCell"]),
            Paragraph(event.get_kind_display(), styles["SmallCell"]),
            Paragraph(duration, styles["SmallCell"]),
            Paragraph(event.get_severity_display(), styles["SmallCell"]),
            Paragraph(event.description, styles["SmallCell"]),
        ])
    if len(rows) == 1:
        rows.append([Paragraph("Sin incidencias", styles["SmallCell"]), "", "", "", ""])
    event_table = Table(rows, colWidths=[35 * mm, 43 * mm, 25 * mm, 25 * mm, 46 * mm], repeatRows=1)
    event_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173b35")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f8f6")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d4ddd9")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(event_table)
    document.build(story, onFirstPage=page_footer, onLaterPages=page_footer)
    return output.getvalue()


def Incident_label(kind):
    from apps.intentos.models import Incident

    return Incident.Kind(kind).label


def create_and_email_report(attempt_id):
    with transaction.atomic():
        attempt = Attempt.objects.select_for_update().select_related(
            "exam", "exam__teacher", "student"
        ).get(pk=attempt_id)
        report, _ = AttemptReport.objects.get_or_create(attempt=attempt)
        if not report.pdf:
            pdf_data = build_pdf(attempt)
            report.pdf.save(f"intento_{attempt.pk}.pdf", ContentFile(pdf_data), save=False)
            report.save(update_fields=["pdf"])
        else:
            try:
                report.pdf.open("rb")
                pdf_data = report.pdf.read()
            except Exception:
                pdf_data = build_pdf(attempt)
                report.pdf.save(f"intento_{attempt.pk}.pdf", ContentFile(pdf_data), save=False)
                report.save(update_fields=["pdf"])

        should_send = (
            attempt.status == Attempt.Status.SUBMITTED
            and not report.email_attempted_at
            and bool(attempt.exam.teacher.email)
        )
        if should_send:
            report.email_attempted_at = timezone.now()
            report.save(update_fields=["email_attempted_at"])

    if should_send:
        teacher = attempt.exam.teacher
        try:
            message = EmailMessage(
                subject=f"Informe de evaluación: {attempt.exam.title}",
                body=(
                    f"El intento de {attempt.student.get_full_name() or attempt.student.username} "
                    f"finalizó con {attempt.percentage}% de respuestas correctas. "
                    f"Nivel de sospecha calculado: {attempt.suspicion_level}. "
                    "El indicador no modifica la calificación."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[teacher.email],
            )
            message.attach(f"informe_intento_{attempt.pk}.pdf", pdf_data, "application/pdf")
            message.send(fail_silently=True)
            AttemptReport.objects.filter(pk=report.pk).update(email_sent_at=timezone.now())
        except Exception:
            pass
    return report