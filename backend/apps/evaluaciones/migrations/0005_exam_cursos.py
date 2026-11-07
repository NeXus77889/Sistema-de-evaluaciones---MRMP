from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [("evaluaciones", "0004_role_choice_limits")]

    operations = [
        migrations.AddField(
            model_name="exam",
            name="cursos",
            field=models.ManyToManyField(
                blank=True,
                related_name="examenes",
                to="evaluaciones.curso",
            ),
        ),
    ]