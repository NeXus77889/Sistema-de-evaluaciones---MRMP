from django.core.management.base import BaseCommand, CommandError

from apps.usuarios.services import NominaImportError, importar_nomina


class Command(BaseCommand):
    help = "Importa estudiantes y cursos desde un archivo Excel de nómina."

    def add_arguments(self, parser):
        parser.add_argument("archivo", help="Ruta del archivo Excel .xlsx o .xls")

    def handle(self, *args, **options):
        filename = options["archivo"]
        try:
            with open(filename, "rb") as source:
                summary = importar_nomina(source, filename)
        except OSError as error:
            raise CommandError(f"No se pudo abrir el archivo: {error}") from error
        except NominaImportError as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                "Importación completada: "
                f"{summary['filas']} filas, "
                f"{summary['estudiantes_creados']} estudiantes creados, "
                f"{summary['estudiantes_actualizados']} actualizados, "
                f"{summary['cursos_creados']} cursos creados, "
                f"{summary['cursos_actualizados']} actualizados."
            )
        )
        if summary["claves_temporales"]:
            credentials = "; ".join(
                f"{identification}: {password}"
                for identification, password in summary["claves_temporales"]
            )
            self.stdout.write(
                self.style.WARNING(
                    "Claves temporales (entregar al estudiante): " + credentials
                )
            )