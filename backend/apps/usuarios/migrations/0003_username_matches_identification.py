from django.db import migrations
from django.db.models import Count, F


def match_usernames_to_identification(apps, schema_editor):
    User = apps.get_model("usuarios", "User")
    database = schema_editor.connection.alias
    users = User.objects.using(database)
    duplicates = (
        users.exclude(identification="")
        .values("identification")
        .annotate(total=Count("pk"))
        .filter(total__gt=1)
    )
    if duplicates.exists():
        raise RuntimeError("Hay cédulas duplicadas; corrígelas antes de migrar usuarios.")

    targets = list(users.exclude(identification="").exclude(username=F("identification")))
    for user in targets:
        conflict = users.filter(username=user.identification).exclude(pk=user.pk).first()
        if conflict and not conflict.identification:
            raise RuntimeError(
                "Una cédula está ocupada por una cuenta sin identificación; resuelve el conflicto antes de migrar."
            )

    for user in targets:
        temporary_username = f"__cedula_migration_{user.pk}__"
        while users.filter(username=temporary_username).exclude(pk=user.pk).exists():
            temporary_username += "_"
        users.filter(pk=user.pk).update(username=temporary_username)
    for user in targets:
        users.filter(pk=user.pk).update(username=user.identification)


class Migration(migrations.Migration):
    dependencies = [("usuarios", "0002_role_and_password_policy")]

    operations = [migrations.RunPython(match_usernames_to_identification, migrations.RunPython.noop)]