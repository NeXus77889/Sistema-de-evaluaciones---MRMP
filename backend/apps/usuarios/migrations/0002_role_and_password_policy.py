from django.db import migrations, models


def forwards_role_values(apps, schema_editor):
    User = apps.get_model("usuarios", "User")
    for old_value, new_value in (("admin", "ADMIN"), ("teacher", "DOCENTE"), ("student", "ESTUDIANTE")):
        User.objects.filter(rol=old_value).update(rol=new_value)


def backwards_role_values(apps, schema_editor):
    User = apps.get_model("usuarios", "User")
    for old_value, new_value in (("ADMIN", "admin"), ("DOCENTE", "teacher"), ("ESTUDIANTE", "student")):
        User.objects.filter(rol=old_value).update(rol=new_value)


class Migration(migrations.Migration):

    dependencies = [("usuarios", "0001_initial")]

    operations = [
        migrations.RenameField(model_name="user", old_name="role", new_name="rol"),
        migrations.RunPython(forwards_role_values, backwards_role_values),
        migrations.AlterField(
            model_name="user",
            name="rol",
            field=models.CharField(
                choices=[("ADMIN", "Administrador"), ("DOCENTE", "Docente"), ("ESTUDIANTE", "Estudiante")],
                default="ESTUDIANTE",
                max_length=12,
                verbose_name="rol",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="debe_cambiar_password",
            field=models.BooleanField(default=True, verbose_name="debe cambiar contraseña"),
        ),
    ]