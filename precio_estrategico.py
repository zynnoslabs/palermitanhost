"""
precio_estrategico.py — Calculador de precio estratégico para Palermitan Host
Combina datos de mercado con factores propios de la propiedad para sugerir precio óptimo.
"""
from datetime import datetime
import math

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

    mes = fecha.month
    dia_semana = fecha.weekday()  # 0=lunes, 4=viernes, 5=sábado, 6=domingo
    es_fin_de_semana = dia_semana in (4, 5, 6)  # viernes a domingo

    nombre_temporada, mult_temporada = TEMPORADA_MULTIPLICADORES.get(mes, ("Media", 1.00))

    # ── Paso 1: base = mediana del mercado ──────────────────────────────────
    precio_base = mercado.get("mediana", 30000)
    pasos = [{
        "paso": 1,
        "descripcion": "Mediana de mercado (Palermo, misma categoría)",
        "valor": precio_base,
        "multiplicador": 1.0,
        "acumulado": precio_base,
    }]

    # ── Paso 2: ajuste por rating vs zona ────────────────────────────────────
    rating_prop = float(propiedad.get("rating", 4.5) or 4.5)
    rating_zona = float(mercado.get("rating_promedio_zona", 4.5) or 4.5)
    diff_rating = rating_prop - rating_zona
    # ±6% por cada 0.1 de diferencia, capped entre -12% y +18%
    mult_rating = 1.0 + max(-0.12, min(0.18, diff_rating * 0.6))
    precio_paso2 = precio_base * mult_rating
    pasos.append({
        "paso": 2,
        "descripcion": f"Ajuste por rating ({rating_prop:.1f} vs zona {rating_zona:.1f})",
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
        "descripcion": f"Temporada {nombre_temporada} (mes {mes})",
        "valor": precio_paso4,
        "multiplicador": mult_temporada,
        "acumulado": precio_paso4,
    })

    # ── Paso 5: ocupación histórica ───────────────────────────────────────────
    pct_ocupacion = _calcular_ocupacion(reservas_historicas)
    mult_ocup = _mult_ocupacion(pct_ocupacion)
    precio_paso5 = precio_paso4 * mult_ocup
    pasos.append({
        "paso": 5,
        "descripcion": f"Ocupación histórica ({pct_ocupacion:.0f}% últimos 90 días)",
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

    # ── Redondear a múltiplo de $500 ──────────────────────────────────────────
    precio_sugerido = round(precio_final / 500) * 500
    precio_minimo = round(precio_final * 0.85 / 500) * 500
    precio_maximo = round(precio_final * 1.20 / 500) * 500

    explicacion = (
        f"Precio calculado en base a la mediana de mercado de Palermo "
        f"(${precio_base:,.0f}), ajustado por el rating de la propiedad "
        f"({rating_prop:.1f} vs {rating_zona:.1f} zona), sus {reviews} reseñas, "
        f"la temporada {nombre_temporada} de {'diciembre' if mes==12 else 'mes ' + str(mes)}, "
        f"ocupación histórica del {pct_ocupacion:.0f}%"
        + (" y recargo de fin de semana." if es_fin_de_semana else ".")
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
    """Calcula % de días ocupados en los últimos 90 días."""
    if not reservas_historicas:
        return 40  # default moderado

    hoy = datetime.now().date()
    desde = hoy - __import__("datetime").timedelta(days=90)
    dias_ocupados = set()

    for r in reservas_historicas:
        try:
            fi = r.get("fecha_inicio")
            ff = r.get("fecha_fin")
            if not fi or not ff:
                continue
            if isinstance(fi, str):
                fi = datetime.fromisoformat(fi).date()
            if isinstance(ff, str):
                ff = datetime.fromisoformat(ff).date()
            d = fi
            while d < ff:
                if desde <= d <= hoy:
                    dias_ocupados.add(d)
                d += __import__("datetime").timedelta(days=1)
        except Exception:
            pass

    return (len(dias_ocupados) / 90) * 100
