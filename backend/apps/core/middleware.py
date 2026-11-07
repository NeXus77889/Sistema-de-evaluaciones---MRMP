from django.shortcuts import redirect
from django.urls import reverse

from apps.usuarios.models import User


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        allowed_paths = {
            reverse("password-change"),
            reverse("logout"),
            reverse("create-support-ticket"),
        }
        if (
            user.is_authenticated
            and user.debe_cambiar_password
            and user.rol in {User.Role.TEACHER, User.Role.STUDENT}
            and request.path_info not in allowed_paths
        ):
            return redirect("password-change")
        return self.get_response(request)