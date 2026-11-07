from django.db import migrations


COURSE_NAMES = {
    "INIC-1-PARA-A": "1º Inicial A",
    "INIC-2-PARA-A": "2º Inicial A",
    "PRIM-GRAD-PARA-A": "1º EGB A",
    "SEGU-GRAD-PARA-A": "2º EGB A",
    "SEGU-GRAD-PARA-B": "2º EGB B",
    "TERC-GRAD-PARA-A": "3º EGB A",
    "TERC-GRAD-PARA-B": "3º EGB B",
    "CUAR-GRAD-PARA-A": "4º EGB A",
    "CUAR-GRAD-PARA-B": "4º EGB B",
    "QUIN-GRAD-PARA-A": "5º EGB A",
    "QUIN-GRAD-PARA-B": "5º EGB B",
    "SEXT-GRAD-PARA-A": "6º EGB A",
    "SEXT-GRAD-PARA-B": "6º EGB B",
    "SEPT-GRAD-PARA-A": "7º EGB A",
    "SEPT-GRAD-PARA-B": "7º EGB B",
    "OCTA-GRAD-PARA-A": "8º EGB A",
    "OCTA-GRAD-PARA-B": "8º EGB B",
    "NOVE-GRAD-PARA-A": "9º EGB A",
    "NOVE-GRAD-PARA-B": "9º EGB B",
    "DECI-GRAD-PARA-A": "10º EGB A",
    "DECI-GRAD-PARA-B": "10º EGB B",
    "PRIM-CURS-CIEN-PARA": "1º BGU Ciencias A",
    "PRIM-CURS-CONT-PARA": "1º BGU Contabilidad A",
    "PRIM-CURS-INFO-PARA": "1º BGU Informática A",
    "SEGU-CURS-CIEN-PARA": "2º BGU Ciencias A",
    "SEGU-CURS-CONT-PARA": "2º BGU Contabilidad A",
    "SEGU-CURS-INFO-PARA": "2º BGU Informática A",
    "TERC-CURS-CIEN-PARA": "3º BGU Ciencias B",
    "TERC-CURS-CONT-PARA": "3º BGU Contabilidad A",
    "TERC-CURS-INFO-PARA": "3º BGU Informática A",
}


def normalize_course_names(apps, schema_editor):
    Curso = apps.get_model("evaluaciones", "Curso")
    for codigo, nombre in COURSE_NAMES.items():
        Curso.objects.filter(codigo=codigo).update(nombre=nombre)
    course, created = Curso.objects.get_or_create(
        codigo="TERC-BGU-CIEN-A",
        defaults={"nombre": "3º BGU Ciencias A"},
    )
    if not created and course.nombre != "3º BGU Ciencias A":
        course.nombre = "3º BGU Ciencias A"
        course.save(update_fields=["nombre"])


class Migration(migrations.Migration):
    dependencies = [("evaluaciones", "0005_exam_cursos")]

    operations = [migrations.RunPython(normalize_course_names, migrations.RunPython.noop)]