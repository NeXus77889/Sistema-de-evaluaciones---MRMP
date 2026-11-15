import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("evaluaciones", "0003_academic_control"),
        ("usuarios", "0002_role_and_password_policy"),
    ]

    operations = [
        migrations.AlterField(
            model_name="curso",
            name="estudiantes",
            field=models.ManyToManyField(
                blank=True,
                limit_choices_to={"rol": "ESTUDIANTE"},
                related_name="cursos",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="asignaciondocente",
            name="docente",
            field=models.ForeignKey(
                limit_choices_to={"rol": "DOCENTE"},
                on_delete=django.db.models.deletion.PROTECT,
                related_name="asignaciones_docentes",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="exam",
            name="teacher",
            field=models.ForeignKey(
                limit_choices_to={"rol": "DOCENTE"},
                on_delete=django.db.models.deletion.PROTECT,
                related_name="created_exams",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="exam",
            name="students",
            field=models.ManyToManyField(
                blank=True,
                limit_choices_to={"rol": "ESTUDIANTE"},
                related_name="assigned_exams",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]