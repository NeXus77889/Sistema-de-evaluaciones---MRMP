import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("intentos", "0002_initial"),
        ("usuarios", "0002_role_and_password_policy"),
    ]

    operations = [
        migrations.AlterField(
            model_name="attempt",
            name="student",
            field=models.ForeignKey(
                limit_choices_to={"rol": "ESTUDIANTE"},
                on_delete=django.db.models.deletion.PROTECT,
                related_name="attempts",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]