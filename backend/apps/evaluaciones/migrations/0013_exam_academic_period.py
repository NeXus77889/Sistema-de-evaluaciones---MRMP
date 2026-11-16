from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("evaluaciones", "0012_tarea_nota_maxima_alter_entregatarea_calificacion"),
    ]

    operations = [
        migrations.AddField(
            model_name="exam",
            name="trimestre",
            field=models.PositiveSmallIntegerField(
                blank=True,
                choices=[(1, "Primer trimestre"), (2, "Segundo trimestre"), (3, "Tercer trimestre")],
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="exam",
            name="parcial",
            field=models.PositiveSmallIntegerField(
                blank=True,
                choices=[(1, "Primer parcial"), (2, "Segundo parcial")],
                null=True,
            ),
        ),
    ]
