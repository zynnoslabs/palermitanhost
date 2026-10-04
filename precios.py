# precios.py
# Fórmula determinística de precio sugerido por noche.
# La IA solo redacta la justificación; no inventa números.

from datetime import date
import statistics


def calcular_precio_sugerido(propiedad, reservas_historicas, competencia_barrio,
                              fecha_desde, fecha_hasta):
    """
    Devuelve dict con:
      precio_minimo    : costo de break-even por noche
      precio_sugerido  : precio recomendado
      precio_maximo    : techo basado en competencia
      detalle          : dict con cada componente para mostrar en pantalla
    """
    # ── 1. Precio mínimo (break-even) ──────────────────────────────────────
    # Costos fijos mensuales / 30 + precio base como piso
    costos_mes = (
        (propiedad.get("costo_expensas")  or 0) +
        (propiedad.get("costo_servicios") or 0) +
        (propiedad.get("costo_limpieza")  or 0) +
        (propiedad.get("costo_comision")  or 0)
    )
    costo_por_noche = round(costos_mes / 30.44, 2)
    precio_base     = propiedad.get("precio_base") or 0
    precio_minimo   = max(precio_base, costo_por_noche * 1.1)  # +10% margen mínimo

    # ── 2. Mediana de la competencia ────────────────────────────────────────
    precios_comp = [c.get("precio_noche",0) for c in competencia_barrio if c.get("precio_noche",0) > 0]
    mediana_comp = round(statistics.median(precios_comp), 2) if precios_comp else None

    # ── 3. Factor temporada ─────────────────────────────────────────────────
    d1 = date.fromisoformat(fecha_desde)
    mes = d1.month
    TEMPORADA = {
        1:'alta',2:'alta',3:'media',4:'media',
        5:'baja',6:'baja',7:'media',8:'media',
        9:'baja',10:'baja',11:'media',12:'alta'
    }
    temporada = TEMPORADA.get(mes, 'media')
    factor_temporada = {'alta': 1.25, 'media': 1.0, 'baja': 0.85}[temporada]

    # ── 4. Factor fin de semana ─────────────────────────────────────────────
    dias_finde = sum(1 for i in range((date.fromisoformat(fecha_hasta) - d1).days + 1)
                     if (d1.toordinal() + i) % 7 in (5, 6))  # sáb=5, dom=6
    total_dias = max((date.fromisoformat(fecha_hasta) - d1).days + 1, 1)
    proporcion_finde = dias_finde / total_dias
    factor_finde = 1 + (proporcion_finde * 0.10)  # hasta +10% si todo es finde

    # ── 5. Factor ocupación histórica ───────────────────────────────────────
    # Si la tasa histórica en esas fechas es alta, subir precio
    noches_hist = sum(r.get("noches",0) or 0 for r in reservas_historicas)
    dias_hist   = 365  # base anual simple
    tasa_hist   = min(noches_hist / dias_hist, 1.0) if dias_hist > 0 else 0
    factor_ocup = 1 + (tasa_hist * 0.15)  # hasta +15% si ocupación histórica es 100%

    # ── 6. Precio sugerido ──────────────────────────────────────────────────
    base_calculo = mediana_comp if mediana_comp else precio_minimo * 1.3
    precio_sugerido = round(
        base_calculo * factor_temporada * factor_finde * factor_ocup, 2
    )
    precio_sugerido = max(precio_sugerido, precio_minimo)

    # ── 7. Precio máximo ────────────────────────────────────────────────────
    precio_maximo = round(
        (mediana_comp * 1.20) if mediana_comp else precio_sugerido * 1.30, 2
    )

    return {
        "precio_minimo":   round(precio_minimo, 2),
        "precio_sugerido": precio_sugerido,
        "precio_maximo":   precio_maximo,
        "detalle": {
            "costo_por_noche":    costo_por_noche,
            "precio_base":        precio_base,
            "mediana_competencia": mediana_comp,
            "n_competidores":     len(precios_comp),
            "temporada":          temporada,
            "factor_temporada":   factor_temporada,
            "proporcion_finde":   round(proporcion_finde * 100, 1),
            "factor_finde":       round(factor_finde, 3),
            "tasa_ocupacion_hist": round(tasa_hist * 100, 1),
            "factor_ocupacion":   round(factor_ocup, 3),
        }
    }
