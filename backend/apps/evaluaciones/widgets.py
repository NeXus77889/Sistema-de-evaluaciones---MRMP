from django import forms


class GroupedCourseCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    template_name = "widgets/grouped_course_checkboxes.html"

    class Media:
        js = ("js/course_picker.js",)