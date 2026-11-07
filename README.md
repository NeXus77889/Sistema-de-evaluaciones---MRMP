# Sistema de evaluaciones con proctoring web

Aplicación web modular con Django 5.2, Django REST Framework, plantillas Django, JavaScript nativo, MySQL 8 y ReportLab. Está orientada a Python 3.12.

## Requisitos

- Python 3.12.
- MySQL Server 8 con una base de datos `utf8mb4`.
- Bibliotecas de desarrollo necesarias para compilar `mysqlclient`.
- Navegador moderno con cámara y micrófono para realizar una evaluación. `getUserMedia` requiere HTTPS, excepto en `localhost`.

En Debian/Ubuntu, instala las dependencias de compilación antes de instalar los requisitos Python:

```bash
sudo apt update
sudo apt install build-essential pkg-config python3.12-dev default-libmysqlclient-dev
```

El proyecto no inicia ni instala MySQL automáticamente. El script [database/scripts/create_database.sql](database/scripts/create_database.sql) crea la base; configura usuario y permisos de MySQL por separado.

## Instalación

Desde la raíz del proyecto:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
cp .env.example .env
```

Edita `.env` y configura una clave secreta, las credenciales de MySQL y los datos SMTP. La aplicación normal usa siempre `django.db.backends.mysql`; no hay selector de SQLite en la configuración de ejecución.

```bash
mysql -u root -p < database/scripts/create_database.sql
cd backend
python manage.py check
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

El superusuario creado queda en el rol administrador. Entra en `http://127.0.0.1:8000/admin/` para crear cuentas de docentes y estudiantes. Usa roles docentes/estudiantes y asigna estudiantes a las evaluaciones desde el editor docente.

## Importación de nóminas

La nómina debe ser un archivo `.xlsx` o `.xls` con las columnas `identificacion`, `nombres`, `apellidos`, `email`, `curso_codigo` y `curso_nombre` en la primera fila. Puedes importarla desde **Admin > Cursos > Importar nómina** o desde la terminal:

```bash
cd backend
python manage.py importar_nomina ruta/al/archivo.xlsx
```

Los estudiantes se identifican por cédula, se actualizan y trasladan al curso de la nómina. Las cuentas nuevas o actualizadas reciben una clave temporal y deben cambiarla antes de acceder al resto del sistema. El resultado se muestra en una tabla del Admin con filtros, impresión y descarga CSV; las claves también se almacenan en la base solo como hash.

Para docentes, usa un archivo `.xlsx` o `.csv` con columnas `Cedula`, `Apellidos`, `Nombres`, `Email`, `Materia(s)` y `Curso(s)`. Materias y cursos pueden separarse con coma o punto y coma; listas de la misma longitud se emparejan por posición. También puedes importar desde **Admin > Cursos > Importar docentes**:

```bash
cd backend
python manage.py importar_docentes ruta/al/archivo.xlsx
```

Las asignaciones se relacionan por docente, materia y curso, y las claves temporales aparecen en el mismo reporte protegido del Admin.

Para SMTP, configura `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` y `DEFAULT_FROM_EMAIL`. Sin credenciales SMTP válidas, la generación del PDF puede completarse, pero el correo fallará y quedará registrado en los logs.

## Pruebas

Las pruebas usan una base SQLite `:memory:` mediante un módulo de configuración aislado; nunca usan ni cambian la base configurada para la aplicación.

```bash
cd backend
DJANGO_SETTINGS_MODULE=config.test_settings python manage.py test
python manage.py makemigrations --check --dry-run
```

No uses `config.test_settings` para ejecutar la aplicación o las migraciones de desarrollo/producción. Para validar conexión y migraciones de MySQL, configura el servicio y credenciales reales y ejecuta `python manage.py check` y `python manage.py migrate` sin cambiar `DJANGO_SETTINGS_MODULE`.

## Alcance funcional

- Roles administrador, docente y estudiante; autenticación y permisos por propiedad.
- Evaluaciones con asignación individual, disponibilidad, duración, preguntas de opción múltiple y una opción correcta.
- Un intento por estudiante y evaluación; guardado de respuestas en servidor, recuperación tras recargar, entrega manual y entrega al vencer el plazo.
- Cámara y micrófono solicitados antes de iniciar. Se registran pérdida de foco/visibilidad y cambios de estado de las pistas locales.
- Calificación calculada en el backend. Las respuestas correctas no se envían al navegador del estudiante.
- Análisis configurable, informe PDF privado y un intento de envío SMTP por intento finalizado.

Las señales del navegador son indicadores que requieren revisión contextual. No prueban plagio, no alteran la calificación y no detectan todas las aplicaciones o dispositivos externos. Más detalle en [docs/architecture.md](docs/architecture.md) y [docs/suspicion-scoring.md](docs/suspicion-scoring.md).

## Configuración sensible

No publiques `.env`, informes privados, volcados de base de datos ni credenciales SMTP. En producción, sirve el sitio sobre HTTPS, configura `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, cookies seguras y almacenamiento privado para PDFs. El servidor de desarrollo de Django no es para producción.