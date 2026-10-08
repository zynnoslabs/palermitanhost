# ia.py
# Comunicación con Groq API.
# Dos funciones principales: generar_informe() y responder_huesped().
# Nunca recibe datos personales de huéspedes (nombres, teléfonos, emails).

import os
from groq import Groq

# ### CAMBIO AQUÍ ### — Groq dio de baja llama-3.3-70b-versatile (16/08/2026); usa gpt-oss-120b
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
# ### CAMBIO AQUÍ ### — modelo rápido para tareas cortas (huéspedes, reseñas, resúmenes).
# En Groq cada modelo tiene su propio límite diario: repartir el uso evita quedarse sin cupo.
GROQ_MODEL_RAPIDO = os.getenv("GROQ_MODEL_RAPIDO", "openai/gpt-oss-20b")


def extra_modelo(modelo, esfuerzo="low"):
    """gpt-oss 'piensa' antes de responder: se baja el esfuerzo para que sea rápido."""
    return {"reasoning_effort": esfuerzo} if str(modelo).startswith("openai/gpt-oss") else {}


def explicar_error(e):
    """### CAMBIO AQUÍ ### — traduce los errores de Groq a un mensaje claro."""
    t = str(e)
    if "429" in t or "rate_limit" in t or "413" in t:
        import re
        tipo = ("diario" if "per day" in t else "por minuto" if "per minute" in t
                else "por pedido" if "413" in t or "too large" in t else "")
        nums = re.search(r"Limit (\d+), Used (\d+), Requested (\d+)", t)
        detalle = (f" [límite {tipo}: {int(nums.group(1)):,} tokens · usados {int(nums.group(2)):,} · "
                   f"pedidos {int(nums.group(3)):,}]".replace(",", ".") if nums else (f" [límite {tipo}]" if tipo else ""))
        return ("Se alcanzó el límite de uso de Groq (plan gratuito). Probá de nuevo en unos minutos "
                "o activá el plan Dev en console.groq.com/settings/billing." + detalle)
    if "401" in t or "invalid_api_key" in t:
        return "La clave de Groq (GROQ_API_KEY) es inválida o fue revocada."
    if "model_not_found" in t or "decommissioned" in t:
        return "El modelo de IA configurado ya no existe en Groq. Revisá GROQ_MODEL."
    return f"Error al conectar con Groq: {t}"


def completar(mensajes, modelo, max_tokens, temperature=0.3, esfuerzo="low", **extra):
    """### CAMBIO AQUÍ ### — llama a Groq; si el modelo se quedó sin cupo (429) prueba con el otro."""
    otro = GROQ_MODEL_RAPIDO if modelo == GROQ_MODEL else GROQ_MODEL
    error = None
    for m in ([modelo, otro] if otro != modelo else [modelo]):
        try:
            return _cliente().chat.completions.create(
                model=m, messages=mensajes, max_tokens=max_tokens, temperature=temperature,
                **extra_modelo(m, esfuerzo), **extra)
        except Exception as e:
            error = e
            if "429" not in str(e) and "rate_limit" not in str(e):
                break
    raise error


def texto_respuesta(respuesta):
    """Devuelve el texto de la IA o lanza error si vino vacío (sin tokens suficientes)."""
    texto = (respuesta.choices[0].message.content or "").strip()
    if not texto:
        raise RuntimeError("La IA devolvió una respuesta vacía. Probá de nuevo.")
    return texto


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
        respuesta = completar([{"role": "user", "content": prompt}], GROQ_MODEL, 4000, 0.4)
        return texto_respuesta(respuesta)
    except Exception as e:
        raise RuntimeError(explicar_error(e))


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
5. Sé breve y directo, pero respondé con una oración completa y amable (no solo el dato suelto).
6. Los nombres de personas aparecen como "Huésped #número" por privacidad: si nombrás a alguien, escribilo exactamente así.

Respuesta:"""

    try:
        respuesta = completar([{"role": "user", "content": prompt}], GROQ_MODEL_RAPIDO, 1500, 0.3)
        texto = texto_respuesta(respuesta)
        pendiente = "consultar con el anfitrión" in texto.lower() or \
                    "consult" in texto.lower() and "host" in texto.lower()
        return texto, pendiente
    except Exception as e:
        return f"Error al generar respuesta: {explicar_error(e)}", True


# ### CAMBIO AQUÍ ### — borrador de respuesta pública a una reseña
def responder_resena(texto_resena, puntaje=None, nombre_propiedad="la propiedad", huesped_alias=None):
    """Devuelve un borrador de respuesta del anfitrión a una reseña. No inventa datos."""
    estrellas = f"Puntaje: {puntaje}/5" if puntaje else "Puntaje: no informado"
    prompt = f"""Sos el anfitrión de {nombre_propiedad}, un alquiler temporario en Buenos Aires.
Escribí una respuesta pública, breve (máximo 4 oraciones), cordial y profesional a esta reseña.
{estrellas}
{f"Quien escribió la reseña: {huesped_alias}" if huesped_alias else ""}
Reseña: "{texto_resena}"

Reglas:
1. Respondé en el mismo idioma de la reseña.
2. Agradecé. Si hay una queja, reconocela sin discutir y decí que se va a tener en cuenta.
3. No prometas descuentos ni inventes datos.
4. Los nombres de personas aparecen como "Huésped #número" por privacidad: si nombrás a alguien,
   escribilo exactamente así (el sistema lo cambia por el nombre real).
Respuesta:"""
    try:
        r = completar([{"role": "user", "content": prompt}], GROQ_MODEL_RAPIDO, 1200, 0.4)
        return texto_respuesta(r)
    except Exception as e:
        raise RuntimeError(explicar_error(e))


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
        "moneda":             "Moneda de todos los montos",            # ### CAMBIO AQUÍ ###
        "tipo_cambio":        "Tipo de cambio usado (pesos por dólar)",
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
