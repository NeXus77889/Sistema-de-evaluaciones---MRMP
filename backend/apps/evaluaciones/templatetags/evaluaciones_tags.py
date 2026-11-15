from django import template
from apps.evaluaciones.academic import format_action_repr, format_course_name

register = template.Library()


@register.filter(name="format_course_name")
def filter_format_course_name(value):
    return format_course_name(value)


@register.filter(name="format_action_repr")
def filter_format_action_repr(value):
    return format_action_repr(value)

