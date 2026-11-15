from django.core.management.base import BaseCommand, CommandError

from apps.usuarios.services import NominaImportError, importar_personal


class Command(BaseCommand):
    help = (
        "Importa la plantilla de personal institucional (docentes y administrativos) "
        "desde un archivo Excel o CSV."
    )

    def add_arguments(self, parser):
        parser.add_argument("archivo", help="Ruta de la plantilla .xlsx, .xls o .csv")

    def handle(self, *args, **options):
        filename = options["archivo"]
        try:
            with open(filename, "rb") as source:
                summary = importar_personal(source, filename)
        except OSError as error:
            raise CommandError(f"No se pudo abrir el archivo: {error}") from error
        except NominaImportError as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                f"Importación completada: {summary['docentes_creados']} docentes y "
                f"{summary['administrativos_creados']} administrativos creados; "
                f"{summary['docentes_actualizados'] + summary['administrativos_actualizados']} "
                f"actualizados; {summary['asignaciones']} asignaciones; "
                f"{summary['omitidos']} omitidos."
            )
        )
        omitted = [row for row in summary["reporte"] if row["rol"] == "No importado"]
        for row in omitted:
            self.stdout.write(
                self.style.WARNING(
                    f"{row['identificacion']} {row['nombres']} ({row['curso']}): "
                    f"{row['clave_temporal']}"
                )
            )
        if summary["claves_temporales"]:
            self.stdout.write(
                "Las cuentas nuevas ingresan con su cédula como clave y deben cambiarla."
            )
