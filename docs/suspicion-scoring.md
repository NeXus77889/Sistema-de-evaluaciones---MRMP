# Metodología del índice de sospecha

El índice ordena señales observables para revisión contextual. No determina plagio, no es una probabilidad y no modifica la nota académica.

| Señal | Peso inicial |
| --- | ---: |
| Pestaña no visible | 12 |
| Pérdida de foco | 8 |
| Cámara desconectada | 20 |
| Micrófono desconectado | 20 |
| Cámara desactivada | 14 |
| Micrófono desactivado | 14 |

Para cada incidente se añade un punto por cada 30 segundos completos de duración, con un máximo de 20 puntos adicionales por evento. Si no se conoce duración, no se añade componente de duración. El total se suma y se limita a 100.

- **BAJO:** 0–19 puntos.
- **MEDIO:** 20–49 puntos.
- **ALTO:** 50–100 puntos.

Los seis pesos y los dos umbrales se pueden ajustar con estas variables de entorno: `PROCTOR_WEIGHT_TAB_HIDDEN`, `PROCTOR_WEIGHT_WINDOW_BLUR`, `PROCTOR_WEIGHT_CAMERA_LOST`, `PROCTOR_WEIGHT_MICROPHONE_LOST`, `PROCTOR_WEIGHT_CAMERA_MUTED`, `PROCTOR_WEIGHT_MICROPHONE_MUTED`, `PROCTOR_MEDIUM_THRESHOLD` y `PROCTOR_HIGH_THRESHOLD`.

La puntuación guardada en el intento es una instantánea del análisis al entregar. El PDF incluye el conteo cronológico y una advertencia; el docente puede consultar eventos individuales. Los pesos iniciales son una convención de producto y deben revisarse con docentes y responsables de privacidad antes de producción.