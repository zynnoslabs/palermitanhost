# ia.py
# Comunicación con Groq API.
# Dos funciones principales: generar_informe() y responder_huesped().
# Nunca recibe datos personales de huéspedes (nombres, teléfonos, emails).

import os
from groq import Groq

GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


def _cliente():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY no configurada en .env")
    return Groq(api_key=api_key)


def generar_informe(metricas_dict, nombre_propiedad=None, periodo=None):
    """
    Genera un informe en español rioplatense a partir de métricas calculadas.
    NO recibe datos personales de huéspedes.

    metricas_dict: dict con ocupación, ADR, RevPAR, ingresos, comparativas, etc.
    Devuelve el texto del informe o lanza excepción si Groq falla.
    """
    prop_str = f"Propiedad: {nombre_propiedad}" if nombre_propiedad else "Análisis general"
    per_str  = f"Período: {periodo}" if periodo else ""

    prompt = f"""Sos un analista inmobiliario especializado en alquileres temporarios en Argentina.
Recibís los siguientes datos de rendimiento y tenés que generar un informe profesional en español rioplatense.

{prop_str}
{per_str}

MÉTRICAS:
{_formatear_metricas(metricas_dict)}

El informe debe tener estas secciones (con ese orden y esos títulos):
## Resumen ejecutivo
(3-4 oraciones con los puntos más importantes)

## Análisis de rendimiento
(Explicá qué significan los números: ocupación, ADR, RevPAR, comparativas)

## Propiedades con mejor y peor rendimiento
(Solo si hay datos de múltiples propiedades; si es una sola, analizá sus tendencias)

## Tendencias y precios del mercado
(Basate en los datos de competencia si están disponibles)

## Riesgos detectados
(Identificá 2-3 riesgos concretos basados en los datos)

## Recomendaciones
(Listá exactamente 3 a 5 acciones concretas y accionables)

Escribí en un tono profesional pero accesible. Usá el voseo argentino.
No inventes datos que no estén en las métricas recibidas."""

    try:
        cliente = _cliente()
        respuesta = cliente.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=2000,
        )
        return respuesta.choices[0].message.content
    except Exception as e:
        raise RuntimeError(f"Error al conectar con Groq: {str(e)}")


def responder_huesped(propiedad_id, mensaje, info_huespedes, nombre_propiedad="la propiedad"):
    """
    Redacta una respuesta para el huésped usando SOLO la info_huespedes cargada.
    Si la respuesta no está en esa info, devuelve (texto, pendiente=True).

    Esta función está diseñada para conectarse fácilmente a un channel manager
    o WhatsApp: recibís propiedad_id + mensaje, devolvés (respuesta, pendiente).
    """
    if not info_huespedes or not info_huespedes.strip():
        return (
            "Gracias por tu consulta. Te respondo a la brevedad con todos los detalles.",
            True
        )

    prompt = f"""Sos el asistente virtual de {nombre_propiedad}, un alojamiento temporario.
Tu única fuente de información es la siguiente:

---
{info_huespedes}
---

El huésped te escribió:
"{mensaje}"

Reglas:
1. Respondé ÚNICAMENTE con información que esté en la fuente de arriba.
2. Si la respuesta no está en esa información, decí exactamente: "Voy a consultar con el anfitrión y te respondo a la brevedad." No inventes ni supongas nada.
3. El tono debe ser cordial y profesional.
4. Respondé en el mismo idioma en que escribió el huésped.
5. Sé breve y directo.

Respuesta:"""

    try:
        cliente = _cliente()
        respuesta = cliente.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=600,
        )
        texto = respuesta.choices[0].message.content.strip()
        pendiente = "consultar con el anfitrión" in texto.lower() or \
                    "consult" in texto.lower() and "host" in texto.lower()
        return texto, pendiente
    except Exception as e:
        return f"Error al generar respuesta: {str(e)}", True


def _formatear_metricas(m):
    """Convierte el dict de métricas a texto legible para el prompt."""
    if not m:
        return "(Sin datos disponibles)"
    lineas = []
    mapeo = {
        "total_reservas":     "Total de reservas",
        "noches_ocupadas":    "Noches ocupadas",
        "tasa_ocupacion":     "Tasa de ocupación (%)",
        "adr":                "ADR - Precio promedio por noche",
        "revpar":             "RevPAR",
        "ingreso_bruto":      "Ingreso bruto total",
        "ingreso_neto":       "Ingreso neto (descontando comisiones Airbnb)",
        "costos_periodo":     "Costos fijos del período",
        "ingreso_neto_real":  "Ingreso neto real (descontando todos los costos)",
        "estadias_prom":      "Estadía promedio (noches)",
        "anticipacion_prom":  "Anticipación promedio de reserva (días)",
    }
    for key, label in mapeo.items():
        val = m.get(key)
        if val is not None:
            lineas.append(f"- {label}: {val}")

    # Comparativas si vienen anidadas
    if "var_anterior" in m:
        lineas.append("\nVariación vs período anterior:")
        for k, v in m["var_anterior"].items():
            if v is not None:
                lineas.append(f"  - {k}: {v:+.1f}%")
    if "var_anio_ant" in m:
        lineas.append("\nVariación vs mismo período año anterior:")
        for k, v in m["var_anio_ant"].items():
            if v is not None:
                lineas.append(f"  - {k}: {v:+.1f}%")

    return "\n".join(lineas)
