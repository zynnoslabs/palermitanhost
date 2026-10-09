# metricas.py
# Calcula ocupación, ADR, RevPAR, ingresos netos y comparativas.
# No accede a la DB directamente: recibe listas de dicts.
#
# ### CAMBIO AQUÍ ### — CÓMO SE CUENTA (revisión general):
#  - Cada reserva aporta las NOCHES que caen dentro del período (no todas al mes de entrada).
#    Ej: entra el 28/09 y sale el 05/10 → 3 noches en septiembre y 4 en octubre.
#  - El dinero de la reserva se reparte igual, en proporción a esas noches.
#  - Canceladas: 0 noches; si Airbnb igual pagó algo, ese monto se cuenta el día de entrada.
#  - El ADR (precio promedio por noche) NO incluye la tarifa de limpieza.

from datetime import datetime, date, timedelta
from collections import defaultdict
import calendar
import statistics

MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _parse(s):
    if not s:
        return None
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def fecha_valida(s):
    """### CAMBIO AQUÍ ### 'AAAA-MM-DD' válida → date; cualquier otra cosa → None (para validar la URL)."""
    d = _parse(s)
    return d if d and 2000 <= d.year <= 2100 else None


def dias_en_rango(desde, hasta):
    d1, d2 = _parse(desde), _parse(hasta)
    if not d1 or not d2 or d2 < d1:
        return 0
    return (d2 - d1).days + 1


def _cancelada(r):
    return (r.get("estado") or "") == "cancelada"


def _rango(r):
    """(entrada, salida, noches_totales). Si falta la salida se calcula con las noches."""
    fi = _parse(r.get("fecha_inicio"))
    ff = _parse(r.get("fecha_fin"))
    try:
        n = int(r.get("noches") or 0)
    except (TypeError, ValueError):
        n = 0
    if fi and ff and ff <= fi:
        ff = None
    if fi and not ff and n > 0:
        ff = fi + timedelta(days=n)
    if fi and ff:
        n = (ff - fi).days
    return fi, ff, n


def _parte_en(r, d1, d2):
    """(noches dentro de [d1, d2], fracción del dinero que corresponde a ese período)."""
    fi, ff, n = _rango(r)
    if not fi:
        return 0, 0.0
    if _cancelada(r) or not ff or n <= 0:
        return 0, (1.0 if d1 <= fi <= d2 else 0.0)
    ini, fin = max(fi, d1), min(ff, d2 + timedelta(days=1))
    dentro = max((fin - ini).days, 0)
    return dentro, dentro / n


def filtrar_reservas(reservas, fecha_desde=None, fecha_hasta=None, propiedad_id=None):
    """Reservas de la propiedad que tienen al menos una noche (o su entrada) dentro del período."""
    d1 = _parse(fecha_desde) or date(1900, 1, 1)
    d2 = _parse(fecha_hasta) or date(2999, 12, 31)
    out = []
    for r in reservas:
        if propiedad_id and r.get("propiedad_id") != propiedad_id:
            continue
        noches, frac = _parte_en(r, d1, d2)
        if noches > 0 or frac > 0:
            out.append(r)
    return out


def costos_del_periodo(costos_mensuales, desde, hasta):
    """### CAMBIO AQUÍ ### costo fijo mensual prorrateado por mes calendario (un mes completo = el costo exacto)."""
    d1, d2 = _parse(desde), _parse(hasta)
    if not d1 or not d2 or d2 < d1 or not costos_mensuales:
        return 0.0
    total, d = 0.0, d1
    while d <= d2:
        dias_mes = calendar.monthrange(d.year, d.month)[1]
        fin_mes = date(d.year, d.month, dias_mes)
        tramo = (min(fin_mes, d2) - d).days + 1
        total += costos_mensuales * tramo / dias_mes
        d = fin_mes + timedelta(days=1)
    return round(total, 2)


def calcular_metricas(reservas, fecha_desde, fecha_hasta, costos_fijos_mensuales=0, unidades=1):
    """
    Devuelve dict con: noches_ocupadas, tasa_ocupacion, adr, revpar,
    ingreso_bruto, ingreso_neto, ingreso_neto_real, estadias_prom, anticipacion_prom,
    total_reservas, canceladas, costos_periodo.
    """
    total_dias = dias_en_rango(fecha_desde, fecha_hasta)
    if total_dias <= 0:
        return {}
    d1, d2 = _parse(fecha_desde), _parse(fecha_hasta)

    noches_ocupadas = 0
    ingreso_bruto = ingreso_neto = limpieza = comisiones = 0.0
    estadias, anticipaciones = [], []
    total_reservas = canceladas = 0

    for r in reservas:
        noches, frac = _parte_en(r, d1, d2)
        if noches == 0 and frac == 0:
            continue
        ingreso_bruto += (r.get("ingreso_bruto") or 0) * frac
        ingreso_neto  += (r.get("ingreso_neto") or 0) * frac
        comisiones    += abs(r.get("comision_airbnb") or 0) * frac
        if _cancelada(r):
            canceladas += 1
            continue
        noches_ocupadas += noches
        limpieza += (r.get("limpieza") or 0) * frac
        total_reservas += 1
        _, _, n = _rango(r)
        if n > 0:
            estadias.append(n)
        ant = r.get("anticipacion_dias")
        if ant is not None and ant >= 0:
            anticipaciones.append(ant)

    # con "todas las propiedades" las noches disponibles son días × unidades activas
    noches_disp = total_dias * max(unidades or 1, 1)
    tasa_ocupacion = round(min(noches_ocupadas / noches_disp, 1) * 100, 1) if noches_disp > 0 else 0
    ingreso_alojamiento = max(ingreso_bruto - limpieza, 0)   # ### CAMBIO AQUÍ ### sin la limpieza
    adr = round(ingreso_alojamiento / noches_ocupadas, 2) if noches_ocupadas > 0 else 0
    revpar = round(ingreso_alojamiento / noches_disp, 2) if noches_disp > 0 else 0

    costos_periodo = costos_del_periodo(costos_fijos_mensuales, d1, d2)
    ingreso_neto_real = round(ingreso_neto - costos_periodo, 2)

    return {
        "total_dias":         total_dias,
        "total_reservas":     total_reservas,
        "canceladas":         canceladas,
        "noches_ocupadas":    noches_ocupadas,
        "tasa_ocupacion":     tasa_ocupacion,
        "adr":                adr,
        "revpar":             revpar,
        "ingreso_bruto":      round(ingreso_bruto, 2),
        "ingreso_neto":       round(ingreso_neto, 2),
        "comisiones":         round(comisiones, 2),
        "costos_periodo":     costos_periodo,
        "ingreso_neto_real":  ingreso_neto_real,
        "estadias_prom":      round(statistics.mean(estadias), 1) if estadias else 0,
        "anticipacion_prom":  round(statistics.mean(anticipaciones), 1) if anticipaciones else None,
    }


def ventana_grafico(desde, hasta):
    """### CAMBIO AQUÍ ### el gráfico por mes muestra al menos 12 meses (antes, con el mes en curso, 1 sola barra)."""
    d2 = _parse(hasta) or date.today()
    d1 = _parse(desde) or d2
    y, m = d2.year, d2.month - 11
    while m <= 0:
        m += 12
        y -= 1
    return min(d1.replace(day=1), date(y, m, 1)), d2


def metricas_por_mes(reservas, propiedad_id, desde, hasta):
    """Ingresos y noches por mes {'2026-10': {..., 'etiqueta': 'oct 2026'}} con TODOS los meses del rango."""
    d1, d2 = _parse(desde), _parse(hasta)
    if not d1 or not d2 or d2 < d1:
        return {}
    sel = [r for r in reservas if not propiedad_id or r.get("propiedad_id") == propiedad_id]
    out = {}
    d = d1.replace(day=1)
    while d <= d2:
        fin = date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])
        m = calcular_metricas(sel, d, fin)
        out[f"{d.year}-{d.month:02d}"] = {
            "etiqueta": f"{MESES_CORTOS[d.month - 1]} {d.year}",
            "ingreso_bruto": round(m.get("ingreso_bruto", 0)),
            "ingreso_neto": round(m.get("ingreso_neto", 0)),
            "noches": m.get("noches_ocupadas", 0),
            "reservas": m.get("total_reservas", 0),
        }
        d = fin + timedelta(days=1)
    return out


def comparar_periodos(reservas, fecha_desde, fecha_hasta, propiedad_id=None, unidades=1):
    """
    Compara el período seleccionado con el período anterior y el mismo período del año pasado.
    ### CAMBIO AQUÍ ### respeta la propiedad elegida y la cantidad de unidades.
    """
    from dateutil.relativedelta import relativedelta
    d1 = _parse(fecha_desde)
    d2 = _parse(fecha_hasta)
    if not d1 or not d2:
        return {}

    delta = d2 - d1
    ant_hasta = d1 - relativedelta(days=1)
    ant_desde = ant_hasta - relativedelta(days=delta.days)
    anio_ant_desde = d1 - relativedelta(years=1)
    anio_ant_hasta = d2 - relativedelta(years=1)

    def met(desde, hasta):
        r = filtrar_reservas(reservas, desde.isoformat(), hasta.isoformat(), propiedad_id)
        return calcular_metricas(r, desde.isoformat(), hasta.isoformat(), 0, unidades)

    actual   = met(d1, d2)
    anterior = met(ant_desde, ant_hasta)
    anio_ant = met(anio_ant_desde, anio_ant_hasta)

    def var(a, b, key):
        va = a.get(key, 0) or 0
        vb = b.get(key, 0) or 0
        if vb == 0:
            return None
        return round(((va - vb) / vb) * 100, 1)

    return {
        "actual":   actual,
        "anterior": anterior,
        "anio_ant": anio_ant,
        "var_anterior": {k: var(actual, anterior, k) for k in ("ingreso_bruto", "tasa_ocupacion", "adr")},
        "var_anio_ant": {k: var(actual, anio_ant, k) for k in ("ingreso_bruto", "tasa_ocupacion", "adr")},
    }


# ocupación por día (gráfico "últimos 7 días" del dashboard)
def ocupacion_diaria(reservas, desde, hasta, unidades=1):
    """Devuelve [{fecha, pct}] con el % de unidades ocupadas cada noche."""
    out = []
    d = desde
    while d <= hasta:
        ocupadas = 0
        for r in reservas:
            if _cancelada(r):
                continue
            fi, ff, _ = _rango(r)
            if fi and ff and fi <= d < ff:   # ### CAMBIO AQUÍ ### sin salida ni noches no se inventa 1 noche
                ocupadas += 1
        pct = round(min(ocupadas / max(unidades, 1), 1) * 100)
        out.append({"fecha": d.isoformat(), "pct": pct})
        d += timedelta(days=1)
    return out
