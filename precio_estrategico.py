"""
precio_estrategico.py — Calculador de precio estratégico para Palermitan Host
Combina datos de mercado con factores propios de la propiedad para sugerir precio óptimo.
"""
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import math

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def _es(v, dec=0):
    """### CAMBIO AQUÍ ### número en formato argentino: 45.000 / 4,8"""
    v = float(Decimal(str(v)).quantize(Decimal(1).scaleb(-dec), rounding=ROUND_HALF_UP))
    t = f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return t


def _redondear(v, paso):
    """### CAMBIO AQUÍ ### redondeo comercial (round() de Python redondea 32,5 a 32)."""
    return int((Decimal(str(v)) / paso).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) * paso

# ── Temporadas ──────────────────────────────────────────────────────────────
TEMPORADA_MULTIPLICADORES = {
    1: ("Alta", 1.28),    # Enero — verano, carnaval
    2: ("Alta", 1.15),    # Febrero
    3: ("Media", 1.00),   # Marzo
    4: ("Media", 0.95),   # Abril
    5: ("Baja", 0.88),    # Mayo
    6: ("Baja", 0.85),    # Junio
    7: ("Media", 0.95),   # Julio — vacaciones invierno
    8: ("Baja", 0.88),    # Agosto
    9: ("Media", 0.95),   # Septiembre
    10: ("Media", 1.00),  # Octubre
    11: ("Media-alta", 1.08),  # Noviembre
    12: ("Alta", 1.30),   # Diciembre — fiestas, turismo
}

# ── Reviews → multiplicador ─────────────────────────────────────────────────
def _mult_reviews(cantidad):
    if cantidad >= 50:
        return 1.06
    elif cantidad >= 20:
        return 1.03
    elif cantidad >= 5:
        return 1.00
    elif cantidad >= 1:
        return 0.96
    else:
        return 0.92   # sin reseñas → 8% descuento


# ── Ocupación histórica → multiplicador ─────────────────────────────────────
def _mult_ocupacion(pct):
    """pct: 0-100"""
    if pct >= 85:
        return 1.10
    elif pct >= 70:
        return 1.05
    elif pct >= 50:
        return 1.00
    elif pct >= 30:
        return 0.95
    else:
        return 0.88


def calcular_precio_estrategico(propiedad, mercado, reservas_historicas, fecha=None):
    """
    Calcula precio estratégico para una propiedad.

    Args:
        propiedad: dict con keys: rating, reviews_count, nombre
        mercado: dict con keys: mediana, rating_promedio_zona (output de scraper)
        reservas_historicas: list de dicts con 'fecha_inicio', 'fecha_fin' (últimos 90 días)
        fecha: datetime a calcular (default: hoy)

    Returns:
        dict con precio_sugerido, precio_minimo, precio_maximo, pasos[], etc.
    """
    if fecha is None:
        fecha = datetime.now()
    elif isinstance(fecha, str):   # ### CAMBIO AQUÍ ### antes una fecha en texto rompía el cálculo
        try:
            fecha = datetime.strptime(fecha[:10], "%Y-%m-%d")
        except ValueError:
            fecha = datetime.now()

    mes = fecha.month
    dia_semana = fecha.weekday()  # 0=lunes, 4=viernes, 5=sábado, 6=domingo
    # ### CAMBIO AQUÍ ### noches de viernes y sábado (la del domingo es de baja demanda)
    es_fin_de_semana = dia_semana in (4, 5)

    nombre_temporada, mult_temporada = TEMPORADA_MULTIPLICADORES.get(mes, ("Media", 1.00))

    # ── Paso 1: base = mediana del mercado ──────────────────────────────────
    precio_base = float(mercado.get("mediana") or 0)   # ### CAMBIO AQUÍ ### sin precio inventado de respaldo
    pasos = [{
        "paso": 1,
        "descripcion": f"Mediana de mercado ({mercado.get('cantidad_propiedades', 0)} comparables)",  # ### CAMBIO AQUÍ ###
        "valor": precio_base,
        "multiplicador": 1.0,
        "acumulado": precio_base,
    }]

    # ── Paso 2: ajuste por rating vs zona ────────────────────────────────────
    # ### CAMBIO AQUÍ ### si falta el puntaje propio o el de la zona, no se ajusta (antes asumía 4,5)
    rating_prop = float(propiedad.get("rating") or 0)
    rating_zona = float(mercado.get("rating_promedio_zona") or 0) if mercado.get("rating_real", True) else 0
    if rating_prop and rating_zona:
        diff_rating = rating_prop - rating_zona
        # ±6% por cada 0.1 de diferencia, capped entre -12% y +18%
        mult_rating = 1.0 + max(-0.12, min(0.18, diff_rating * 0.6))
        desc_rating = f"Ajuste por puntaje ({_es(rating_prop, 2)} vs zona {_es(rating_zona, 2)})"
    else:
        mult_rating = 1.0
        desc_rating = ("Puntaje: sin ajuste (cargá tu puntaje de Airbnb en la propiedad)" if not rating_prop
                       else "Puntaje: sin ajuste (la competencia no informa puntajes)")
    precio_paso2 = precio_base * mult_rating
    pasos.append({
        "paso": 2,
        "descripcion": desc_rating,
        "valor": precio_paso2,
        "multiplicador": mult_rating,
        "acumulado": precio_paso2,
    })

    # ── Paso 3: reseñas / reputación ─────────────────────────────────────────
    reviews = int(propiedad.get("reviews_count", 0) or 0)
    mult_rev = _mult_reviews(reviews)
    precio_paso3 = precio_paso2 * mult_rev
    pasos.append({
        "paso": 3,
        "descripcion": f"Reputación ({reviews} reseñas)",
        "valor": precio_paso3,
        "multiplicador": mult_rev,
        "acumulado": precio_paso3,
    })

    # ── Paso 4: temporada ─────────────────────────────────────────────────────
    precio_paso4 = precio_paso3 * mult_temporada
    pasos.append({
        "paso": 4,
        "descripcion": f"Temporada {nombre_temporada.lower()} ({MESES[mes - 1]})",
        "valor": precio_paso4,
        "multiplicador": mult_temporada,
        "acumulado": precio_paso4,
    })

    # ── Paso 5: ocupación histórica ───────────────────────────────────────────
    pct_ocupacion = _calcular_ocupacion(reservas_historicas)
    # ### CAMBIO AQUÍ ### sin reservas cargadas no se baja el precio (antes asumía 40% y lo bajaba 5%)
    mult_ocup = _mult_ocupacion(pct_ocupacion) if pct_ocupacion is not None else 1.0
    precio_paso5 = precio_paso4 * mult_ocup
    pasos.append({
        "paso": 5,
        "descripcion": (f"Ocupación histórica ({pct_ocupacion:.0f}% últimos 90 días)" if pct_ocupacion is not None
                        else "Ocupación histórica: sin reservas cargadas, sin ajuste"),
        "valor": precio_paso5,
        "multiplicador": mult_ocup,
        "acumulado": precio_paso5,
    })

    # ── Paso 6: fin de semana ─────────────────────────────────────────────────
    mult_fds = 1.10 if es_fin_de_semana else 1.00
    precio_final = precio_paso5 * mult_fds
    if es_fin_de_semana:
        pasos.append({
            "paso": 6,
            "descripcion": "Fin de semana (+10%)",
            "valor": precio_final,
            "multiplicador": mult_fds,
            "acumulado": precio_final,
        })

    # ### CAMBIO AQUÍ ### — redondeo según la escala: pesos a $500, dólares de a 5 (o de a 1 si es barato)
    paso_red = 500 if precio_final >= 5000 else (5 if precio_final >= 100 else 1)
    precio_sugerido = _redondear(precio_final, paso_red)
    precio_minimo = _redondear(precio_final * 0.85, paso_red)
    precio_maximo = _redondear(precio_final * 1.20, paso_red)

    explicacion = (
        f"Precio calculado en base a la mediana de los comparables "
        f"({mercado.get('simbolo', '$')} {_es(precio_base)}), ajustado por el puntaje, "
        f"las {reviews} reseñas, la temporada {nombre_temporada.lower()} de {MESES[mes - 1]}"
        + (f", la ocupación histórica del {pct_ocupacion:.0f}%" if pct_ocupacion is not None else "")
        + (" y recargo de fin de semana (viernes o sábado)." if es_fin_de_semana else ".")
    )

    return {
        "precio_sugerido": precio_sugerido,
        "precio_minimo": precio_minimo,
        "precio_maximo": precio_maximo,
        "pasos": pasos,
        "explicacion": explicacion,
        "fecha_calculo": fecha.isoformat(),
        "es_fin_de_semana": es_fin_de_semana,
        "temporada": nombre_temporada,
        "ocupacion_pct": pct_ocupacion,
    }


def _calcular_ocupacion(reservas_historicas):
    """% de noches ocupadas en los últimos 90 días. None si no hay reservas cargadas.
    ### CAMBIO AQUÍ ### usa el mismo cálculo que el Dashboard (antes contaba 91 días sobre 90 → 101%,
    e ignoraba las reservas sin fecha de salida)."""
    if not reservas_historicas:
        return None
    import metricas
    hoy = datetime.now().date()
    desde = hoy - timedelta(days=89)
    # solo reservas futuras (todavía no hay historial cargado): no se ajusta
    if not any((metricas._parse(r.get("fecha_inicio")) or hoy) <= hoy for r in reservas_historicas):
        return None
    m = metricas.calcular_metricas(metricas.filtrar_reservas(reservas_historicas, desde, hoy), desde, hoy, 0, 1)
    return m.get("tasa_ocupacion", 0)
