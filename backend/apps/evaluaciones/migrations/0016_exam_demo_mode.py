from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("evaluaciones", "0015_exam_camera_ai_randomize"),
    ]

    operations = [
        migrations.AddField(
            model_name="exam",
            name="demo_mode",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Para exposiciones: al pulsar Alt durante la evaluación se muestra una alerta "
                    "simulada de dispositivo cercano. No registra incidencias ni afecta la nota."
                ),
                verbose_name="Modo demostración",
            ),
        ),
    ]
