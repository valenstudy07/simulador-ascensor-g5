# Simulador de ascensor regenerativo (Proyecto 10 – G5)

Caso de estudio: edificio de 20 paradas (75 m, 2,5 m/s, 1,0 m/s²), cabina de 950 kg,
carga nominal de 1000 kg, contrapeso equilibrado al 50 % (1450 kg) o al 30 % (1250 kg)
según ISO 25745. Todos los valores están en `parametros.py`.

## Ejecutar

    pip install -r requirements.txt
    streamlit run app.py      # simulador interactivo
    python validacion.py      # tabla de errores Euler/RK4, orden de convergencia y contraste con SciPy
    python dia_tipico.py      # consumo de un día típico (kWh/día) según el perfil de uso de la ISO 25745-2
    python figuras.py         # figuras PNG y tablas CSV para el artículo (carpeta figuras/)

## Archivos

| Archivo | Contenido |
|---|---|
| parametros.py | Datos del caso (FUENTE) y supuestos del modelo (SUPUESTO). Única fuente de valores. |
| modelo.py | Ecuaciones de cabina, contrapeso y polea; control de velocidad; perfil de velocidad. |
| metodos.py | Euler y Runge-Kutta 4 programados a mano. |
| energia.py | Balance de energía, verificación de conservación, barrido de masa, interpretación. |
| simulacion.py | Une modelo + método + balance. |
| validacion.py | Solución analítica, errores, influencia del paso, convergencia, contraste con solve_ivp. |
| app.py | Interfaz Streamlit + Plotly. |
| dia_tipico.py | Consumo diario: viajes y carga media de la ISO 25745-2 + consumo en reposo. |
| figuras.py | Figuras estáticas Matplotlib y tablas CSV. |

## Limitaciones conocidas (declarar en el artículo)

- El perfil de velocidad es trapezoidal: no incluye el jerk de 1,25 m/s³ del caso.
- El día típico usa un solo viaje medio (33 m, carga media 60 kg) como la ISO 25745-2, no una
  distribución real de viajes y cargas. Las potencias de reposo son valores típicos de la norma.
- b, I_polea_eq y Kp son supuestos; la eficiencia (0,85) está dentro del rango 70–85 % de las fuentes.

## Publicar

Subir la carpeta a un repositorio de GitHub y desplegarla en Streamlit Community Cloud
(archivo principal: app.py). El enlace sirve de respaldo para la sustentación y como anexo del artículo.

## Uso de IA

El código fue desarrollado con asistencia de IA (Claude, Anthropic) y revisado por el grupo.
Declararlo en la sección 4 del artículo.
