from django.core.management.base import BaseCommand, CommandError

from apps.usuarios.services import NominaImportError, importar_docentes


class Command(BaseCommand):
    help = "Importa docentes y asignaciones desde un archivo Excel o CSV."

    def add_arguments(self, parser):
        parser.add_argument("archivo", help="Ruta del archivo de docentes .xlsx o .csv")

    def handle(self, *args, **options):
        filename = options["archivo"]
        try:
            with open(filename, "rb") as source:
                summary = importar_docentes(source, filename)
        except OSError as error:
            raise CommandError(f"No se pudo abrir el archivo: {error}") from error
        except NominaImportError as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                f"Importación completada: {summary['filas']} docentes, "
                f"{summary['asignaciones']} asignaciones, "
                f"{summary['docentes_creados']} creados y "
                f"{summary['docentes_actualizados']} actualizados."
            )
        )
        if summary["claves_temporales"]:
            credentials = "; ".join(
                f"{identification}: {password}"
                for identification, password in summary["claves_temporales"]
            )
            self.stdout.write(
                self.style.WARNING(
                    "Claves temporales (entregar al docente): " + credentials
                )
            )