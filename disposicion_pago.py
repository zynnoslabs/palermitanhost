# disposicion_pago.py
# ### CAMBIO AQUÍ ### — Archivo nuevo: "¿Cuánto más podrías cobrar?"
#
# Airbnb no dice cuánto estaba dispuesto a pagar un huésped, pero deja dos pistas en los archivos:
#   1) La ANTICIPACIÓN: si una fecha se vende mucho antes de lo normal, a ese precio sobraba demanda
#      (el precio podía ser más alto). Si se vende a último momento, el precio estaba en el límite.
#   2) El RITMO de ventas: cuánto de las próximas semanas ya está vendido comparado con lo que
#      normalmente estaría vendido a esta altura. Si vas adelantado, podés subir; si vas atrasado, no.
# Todo sale de las reservas que ya están cargadas (archivo de Reservas, columna "Reservada").
# No se toca Airbnb ni se usa IA: son cuentas.

import statistics
from datetime import date, timedelta

import metricas
import monedas

MIN_RESERVAS = 5            # con menos reservas con fecha de reserva no hay base para comparar
VENTANAS = [(0, 13, "Próximas 2 semanas"), (14, 29, "Dentro de 15 a 30 días"),
            (30, 59, "Dentro de 1 a 2 meses"), (60, 89, "Dentro de 2 a 3 meses")]


def _anticipacion(r):
    fr = metricas._parse(r.get("fecha_reserva"))
    fi = metricas._parse(r.get("fecha_inicio"))
    if fr and fi and fi >= fr:
        return (fi - fr).days
    a = r.get("anticipacion_dias")
    try:
        return int(a) if a is not None and int(a) >= 0 else None
    except (TypeError, ValueError):
        return None


def _validas(reservas):
    """Reservas no canceladas, con fechas y noches, con su precio por noche (sin limpieza)."""
    out = []
    for r in reservas:
        if (r.get("estado") or "") == "cancelada":
            continue
        fi, ff, n = metricas._rango(r)
        if not fi or not ff or n <= 0:
            continue
        aloj = max((r.get("ingreso_bruto") or 0) - (r.get("limpieza") or 0), 0)
        out.append({"r": r, "fi": fi, "ff": ff, "n": n, "ant": _anticipacion(r),
                    "fr": metricas._parse(r.get("fecha_reserva")),
                    "precio": round(aloj / n) if aloj > 0 else None})
    return out


def _senal(ant, mediana):
    if ant is None or mediana is None:
        return "—", "neutra"
    if ant >= max(mediana * 1.5, mediana + 14):
        return "Se vendió mucho antes de lo normal: a ese precio sobraba demanda. Para fechas parecidas probá +10%.", "subir"
    if ant <= max(mediana * 0.4, 2):
        return "Se vendió a último momento: ese precio estaba cerca del límite.", "limite"
    return "Ritmo normal.", "neutra"


def _ritmo(validas, hoy):
    """Compara lo ya vendido de cada ventana futura con lo que normalmente estaría vendido a esta altura."""
    pasadas = [v for v in validas if v["fi"] < hoy]
    con_fecha = [v for v in pasadas if v["fr"]]
    if len(con_fecha) < MIN_RESERVAS:
        return None
    inicio = max(min(v["fi"] for v in pasadas), hoy - timedelta(days=365))
    dias_hist = (hoy - inicio).days
    if dias_hist < 60:
        return None
    # ocupación normal (último año, o lo que haya)
    ocupadas = 0
    for v in pasadas:
        a, b = max(v["fi"], inicio), min(v["ff"], hoy)
        ocupadas += max((b - a).days, 0)
    ocup_normal = min(ocupadas / dias_hist, 1)
    # "anticipación por noche": cuántos días antes de cada noche ocupada ya estaba vendida
    leads = []
    for v in con_fecha:
        d = v["fi"]
        while d < v["ff"]:
            leads.append((d - v["fr"]).days)
            d += timedelta(days=1)
    leads.sort()
    total = len(leads)

    def vendida_a_k(k):   # parte de las noches que normalmente ya está vendida k días antes
        import bisect
        return (total - bisect.bisect_left(leads, k)) / total

    futuras = [v for v in validas if v["ff"] > hoy]
    filas = []
    for a, b, nombre in VENTANAS:
        noches = b - a + 1
        vendidas, esperado = 0, 0.0
        for k in range(a, b + 1):
            d = hoy + timedelta(days=k)
            if any(v["fi"] <= d < v["ff"] for v in futuras):
                vendidas += 1
            esperado += ocup_normal * vendida_a_k(k)
        real = vendidas / noches
        esp = esperado / noches
        ratio = real / esp if esp > 0.02 else None
        if vendidas == noches:
            txt, tipo = "Todo vendido. Si se llenó rápido, el precio quedó bajo: la próxima vez subilo 10–15% para esas fechas.", "subir"
        elif ratio is None:
            txt, tipo = "Normalmente a esta altura todavía no hay nada vendido: es temprano para sacar conclusiones.", "neutra"
        elif ratio >= 1.3:
            txt, tipo = "Vas bastante más vendido que lo normal: subí 10% las noches que quedan libres.", "subir"
        elif ratio >= 1.1:
            txt, tipo = "Vas un poco más vendido que lo normal: podés subir 5% las noches libres.", "subir"
        elif ratio >= 0.8:
            txt, tipo = "En línea con lo normal: mantené el precio.", "neutra"
        elif a < 30:
            txt, tipo = "Viene más flojo que lo normal: no subas. Si a 7 días siguen libres, bajá 5–10% o activá una promoción.", "bajar"
        else:
            txt, tipo = "Un poco atrasado, pero falta: mantené y volvé a mirar en una semana.", "neutra"
        filas.append({"nombre": nombre, "vendidas": vendidas, "noches": noches,
                      "real": round(real * 100), "esperado": round(esp * 100), "texto": txt, "tipo": tipo})
    return {"filas": filas, "ocup_normal": round(ocup_normal * 100), "dias_hist": dias_hist}


def analizar(propiedad, reservas, hoy=None, mediana_mercado=None, tc=None):
    """Devuelve el análisis completo para la página de Precios (o None si no hay reservas)."""
    hoy = hoy or date.today()
    mon = propiedad.get("moneda") or "ARS"
    propias = [r for r in reservas if r.get("propiedad_id") == propiedad["id"]]
    if not propias:
        return None
    conv, sin_tc = monedas.convertir_reservas(propias, mon, tc)
    validas = _validas(conv)
    ants = [v["ant"] for v in validas if v["ant"] is not None]
    mediana_ant = round(statistics.median(ants)) if len(ants) >= MIN_RESERVAS else None

    # precios que ya te pagaron (último año)
    precios = sorted(v["precio"] for v in validas if v["precio"] and v["fi"] >= hoy - timedelta(days=365))
    techo = None
    if len(precios) >= 3:
        p90 = precios[min(int(len(precios) * 0.9), len(precios) - 1)]
        techo = {"mediana": round(statistics.median(precios)), "p90": p90, "maximo": precios[-1],
                 "cantidad": len(precios),
                 "sobre_mercado": (sum(1 for p in precios if p > mediana_mercado) if mediana_mercado else None)}

    # últimas reservas: las 10 con llegada más reciente (incluye las que todavía no llegaron)
    recientes = sorted(validas, key=lambda v: v["fi"], reverse=True)[:10]
    filas = []
    for v in recientes:
        txt, tipo = _senal(v["ant"], mediana_ant)
        filas.append({"huesped": v["r"].get("huesped_nombre") or "Huésped", "llegada": v["fi"].isoformat(),
                      "reservo": v["fr"].isoformat() if v["fr"] else None, "ant": v["ant"], "noches": v["n"],
                      "precio": v["precio"],
                      "vs_mercado": (round((v["precio"] / mediana_mercado - 1) * 100) if v["precio"] and mediana_mercado else None),
                      "texto": txt, "tipo": tipo})

    return {"mediana_ant": mediana_ant, "con_fecha": len(ants), "techo": techo, "filas": filas,
            "ritmo": _ritmo(validas, hoy), "sin_tc": sin_tc, "precio_base": propiedad.get("precio_base") or 0,
            "suficiente": len(ants) >= MIN_RESERVAS}


def oportunidad(propiedad, reservas, hoy=None, tc=None):
    """Para las alertas: la primera ventana cercana (≤30 días) que va mucho más vendida que lo normal."""
    a = analizar(propiedad, reservas, hoy, None, tc)
    if not a or not a["ritmo"]:
        return None
    for f in a["ritmo"]["filas"][:2]:
        if f["tipo"] == "subir" and f["vendidas"] < f["noches"] and f["real"] >= f["esperado"] * 1.3 and f["real"] >= 30:
            return f
    return None
