from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager
from django.db import models


class RoleAwareUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields["rol"] = "ADMIN"
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMINISTRATOR = "ADMIN", "Administrador"
        TEACHER = "DOCENTE", "Docente"
        STUDENT = "ESTUDIANTE", "Estudiante"

    email = models.EmailField("correo electrónico", unique=True)
    rol = models.CharField("rol", max_length=12, choices=Role.choices, default=Role.STUDENT)
    debe_cambiar_password = models.BooleanField("debe cambiar contraseña", default=True)
    identification = models.CharField("identificación", max_length=40, blank=True, db_index=True)
    objects = RoleAwareUserManager()

    def save(self, *args, **kwargs):
        if self.identification:
            self.username = self.identification
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = set(update_fields) | {"username"}
        super().save(*args, **kwargs)

    class Meta:
        ordering = ["last_name", "first_name", "username"]
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self):
        return self.get_full_name() or self.username
