from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("evaluaciones", "0014_exam_detect_nearby_ips"),
    ]

    operations = [
        migrations.AddField(
            model_name="exam",
            name="camera_ai_detection",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Analiza la cámara en el navegador del estudiante y registra una incidencia "
                    "si aparece un teléfono o no se ve a la persona. No guarda imágenes."
                ),
                verbose_name="Detección de teléfono por cámara",
            ),
        ),
        migrations.AddField(
            model_name="exam",
            name="randomize_order",
            field=models.BooleanField(
                default=False,
                help_text="Cada estudiante ve las preguntas y las opciones en un orden distinto.",
                verbose_name="Orden aleatorio",
            ),
        ),
    ]
