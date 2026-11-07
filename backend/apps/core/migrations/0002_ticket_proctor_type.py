from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("core", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="ticketatencion",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("PASS", "Recuperar contraseña"),
                    ("USER", "Recuperar usuario o cédula"),
                    ("EXAM", "Consulta de evaluación"),
                    ("PROCTOR", "Incidencia de proctoring"),
                ],
                max_length=8,
            ),
        ),
    ]