# Arquitectura y operación

## Componentes

- `usuarios`: usuario personalizado, correo único, identificación y rol.
- `evaluaciones`: evaluaciones, preguntas, opciones y estudiantes asignados.
- `intentos`: intentos, respuestas, estado y endpoints DRF de examen.
- `monitoreo`: incidencias y servicio puro de puntuación de señales.
- `reportes`: almacenamiento de PDFs, generación y envío SMTP idempotente.
- `core`: autenticación, vistas HTML, dashboards y permisos de presentación.

El modelo `AUTH_USER_MODEL=usuarios.User` está configurado antes de la migración inicial. El ORM es la única capa de acceso a los datos del dominio.

## Persistencia

La configuración normal de `backend/config/settings.py` usa MySQL con `utf8mb4`; conexión y credenciales provienen de variables de entorno. No lee `DB_ENGINE` ni ofrece una alternativa SQLite.

`backend/config/test_settings.py` reemplaza la base solo cuando se solicita explícitamente mediante `DJANGO_SETTINGS_MODULE=config.test_settings`. Su base `:memory:` es temporal y desaparece al cerrar el runner.

## Flujos y permisos

El estudiante solo puede iniciar evaluaciones asignadas y consultar sus propios intentos. El endpoint de estado serializa texto y opciones, nunca `Option.is_correct`. Respuestas e incidencias validan propiedad y pertenencia a la evaluación; la calificación consulta la opción correcta en el backend.

Los docentes solo administran evaluaciones propias y revisan sus intentos. El acceso a resultados individuales del estudiante requiere `results_visible`. Los informes se entregan mediante una vista autenticada, no mediante una URL pública de media.

Los endpoints DRF usan autenticación de sesión, CSRF, permisos autenticados y throttling por usuario. El frontend envía `X-CSRFToken` en las solicitudes mutables.

## API de intentos

- `POST /api/evaluaciones/<exam_id>/iniciar/`
- `GET /api/evaluaciones/intento/<attempt_id>/`
- `POST /api/evaluaciones/intento/<attempt_id>/respuesta/`
- `POST /api/evaluaciones/intento/<attempt_id>/incidencias/`
- `POST /api/evaluaciones/intento/<attempt_id>/entregar/`

Los endpoints requieren sesión iniciada y verifican el rol/propiedad. El identificador de evento UUID hace idempotente el registro frente a reenvíos; el servidor asigna la hora de recepción y la gravedad.

## Integridad del proctoring

El navegador solicita permiso de cámara y micrófono mediante `getUserMedia` antes del inicio. La API puede observar el estado local de las pistas, eventos de foco y Page Visibility. Los navegadores no exponen actividad completa del sistema operativo; un usuario también puede eludir o falsificar señales del cliente. El sistema no captura ni almacena audio o video.

Las señales no son evidencia concluyente de plagio. No se sanciona ni cambia una nota automáticamente. La persona docente revisa eventos individuales y contexto.

## Operación de reportes y correo

La generación del informe se deduplica con relación uno-a-uno al intento. Se marca el intento SMTP antes del envío para evitar correos duplicados ante una repetición del flujo; ante fallo SMTP no se reintenta automáticamente. Se requiere operación manual para investigar el log y, si procede, reintentar de manera controlada.

En producción, configura almacenamiento privado y copias de seguridad fuera del directorio público. Los archivos de informe contienen datos personales y deben seguir las políticas institucionales de retención.