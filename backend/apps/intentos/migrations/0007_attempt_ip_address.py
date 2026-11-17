from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("intentos", "0006_incidentreview"),
    ]

    operations = [
        migrations.AddField(
            model_name="attempt",
            name="ip_address",
            field=models.GenericIPAddressField(
                blank=True,
                null=True,
                verbose_name="IP al iniciar",
            ),
        ),
    ]
