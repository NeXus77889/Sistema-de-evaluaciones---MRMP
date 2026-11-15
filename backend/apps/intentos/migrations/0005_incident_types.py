from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("intentos", "0004_alter_attempt_options")]

    operations = [
        migrations.AlterField(
            model_name="incident",
            name="kind",
            field=models.CharField(
                max_length=24,
                choices=[
                    ("tab_hidden", "Pestaña no visible"),
                    ("window_blur", "Pérdida de foco"),
                    ("camera_lost", "Cámara desconectada"),
                    ("microphone_lost", "Micrófono desconectado"),
                    ("camera_muted", "Cámara desactivada"),
                    ("microphone_muted", "Micrófono desactivado"),
                    ("fullscreen_exit", "Salida de pantalla completa"),
                    ("device_disabled", "Cámara o micrófono desactivado"),
                    ("face_missing", "Rostro no detectado"),
                    ("phone_detected", "Teléfono detectado"),
                ],
            ),
        ),
    ]
