from decimal import Decimal

# ==============================================================================
# CONFIGURACIÓN INSTITUCIONAL DE PONDERACIONES Y CALIFICACIONES
# Ponderaciones configurables de insumos, evaluaciones, tareas y examen final.
# Modificar aquí para ajustar los pesos institucionales.
# ==============================================================================

# Ponderación de insumos dentro de cada parcial (porcentaje sobre 100%)
PESO_INSUMO_1 = Decimal("35.00")           # Tareas y actividades individuales (%)
PESO_INSUMO_2 = Decimal("35.00")           # Lecciones y proyectos grupales (%)
PESO_EVALUACION_PARCIAL = Decimal("30.00") # Evaluación sumativa del parcial (%)

# Ponderación del Examen Final institucional (ejemplo: examen pesa 20%)
PESO_EXAMEN_FINAL = Decimal("20.00")       # Examen final institucional (20%)
PESO_ACTIVIDADES_TRIMESTRE = Decimal("80.00") # Actividades acumuladas del trimestre (80%)

# Ponderación de los 3 trimestres en el promedio anual
PESO_TRIMESTRE_1 = Decimal("30.00")        # Primer Trimestre (%)
PESO_TRIMESTRE_2 = Decimal("35.00")        # Segundo Trimestre (%)
PESO_TRIMESTRE_3 = Decimal("35.00")        # Tercer Trimestre (%)

