import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("evaluaciones", "0002_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Materia",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=100)),
                ("codigo", models.CharField(max_length=20, unique=True)),
            ],
            options={"ordering": ["nombre"], "verbose_name_plural": "materias"},
        ),
        migrations.CreateModel(
            name="Curso",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=100)),
                ("codigo", models.CharField(max_length=20, unique=True)),
                (
                    "estudiantes",
                    models.ManyToManyField(
                        blank=True,
                        limit_choices_to={"role": "student"},
                        related_name="cursos",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["nombre"], "verbose_name_plural": "cursos"},
        ),
        migrations.CreateModel(
            name="AsignacionDocente",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("activo", models.BooleanField(default=True)),
                (
                    "curso",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="asignaciones",
                        to="evaluaciones.curso",
                    ),
                ),
                (
                    "docente",
                    models.ForeignKey(
                        limit_choices_to={"role": "teacher"},
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="asignaciones_docentes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "materia",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="asignaciones",
                        to="evaluaciones.materia",
                    ),
                ),
            ],
            options={
                "verbose_name": "asignación docente",
                "verbose_name_plural": "asignaciones docentes",
                "unique_together": {("docente", "materia", "curso")},
            },
        ),
        migrations.AddField(
            model_name="exam",
            name="materia",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to="evaluaciones.materia"),
        ),
        migrations.AddField(
            model_name="exam",
            name="curso",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to="evaluaciones.curso"),
        ),
    ]