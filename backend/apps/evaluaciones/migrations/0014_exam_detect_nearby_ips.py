from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("evaluaciones", "0013_exam_academic_period"),
    ]

    operations = [
        migrations.AddField(
            model_name="exam",
            name="detect_nearby_ips",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Registra la IP de cada estudiante al iniciar y agrega al informe PDF "
                    "los estudiantes que rindieron desde la misma IP o red."
                ),
                verbose_name="Detectar IPs cercanas",
            ),
        ),
    ]
