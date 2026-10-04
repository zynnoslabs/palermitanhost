# metricas.py
# Calcula ocupación, ADR, RevPAR, ingresos netos y comparativas.
# No accede a la DB directamente: recibe listas de dicts.

from datetime import datetime, date
from collections import defaultdict
import statistics


def _parse(s):
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def dias_en_rango(desde, hasta):
    d1 = _parse(desde) if isinstance(desde, str) else desde
    d2 = _parse(hasta) if isinstance(hasta, str) else hasta
    if not d1 or not d2 or d2 < d1:
        return 0
    return (d2 - d1).days + 1


def filtrar_reservas(reservas, fecha_desde=None, fecha_hasta=None, propiedad_id=None):
    out = []
    for r in reservas:
        if propiedad_id and r.get("propiedad_id") != propiedad_id:
            continue
        fi = _parse(r.get("fecha_inicio"))
        if not fi:
            continue
        if fecha_desde and fi < _parse(fecha_desde):
            continue
        if fecha_hasta and fi > _parse(fecha_hasta):
            continue
        out.append(r)
    return out


def calcular_metricas(reservas, fecha_desde, fecha_hasta, costos_fijos_mensuales=0):
    """
    Devuelve dict con: noches_ocupadas, tasa_ocupacion, adr, revpar,
    ingreso_bruto, ingreso_neto, ingreso_neto_real, estadias_prom, anticipacion_prom,
    total_reservas, costos_periodo.
    """
    total_dias = dias_en_rango(fecha_desde, fecha_hasta)
    if total_dias <= 0:
        return {}

    noches_ocupadas = 0
    ingreso_bruto   = 0.0
    ingreso_neto    = 0.0
    estadias        = []
    anticipaciones  = []

    for r in reservas:
        n = r.get("noches") or 0
        noches_ocupadas += n
        ingreso_bruto   += r.get("ingreso_bruto", 0) or 0
        ingreso_neto    += r.get("ingreso_neto", 0) or 0
        if n > 0:
            estadias.append(n)
        ant = r.get("anticipacion_dias")
        if ant is not None:
            anticipaciones.append(ant)

    tasa_ocupacion = round((noches_ocupadas / total_dias) * 100, 1) if total_dias > 0 else 0
    adr = round(ingreso_bruto / noches_ocupadas, 2) if noches_ocupadas > 0 else 0
    revpar = round(ingreso_bruto / total_dias, 2) if total_dias > 0 else 0

    # Costos: prorratear mensuales al período
    meses_periodo = total_dias / 30.44
    costos_periodo = round(costos_fijos_mensuales * meses_periodo, 2)
    ingreso_neto_real = round(ingreso_neto - costos_periodo, 2)

    return {
        "total_dias":         total_dias,
        "total_reservas":     len(reservas),
        "noches_ocupadas":    noches_ocupadas,
        "tasa_ocupacion":     tasa_ocupacion,
        "adr":                adr,
        "revpar":             revpar,
        "ingreso_bruto":      round(ingreso_bruto, 2),
        "ingreso_neto":       round(ingreso_neto, 2),
        "costos_periodo":     costos_periodo,
        "ingreso_neto_real":  ingreso_neto_real,
        "estadias_prom":      round(statistics.mean(estadias), 1) if estadias else 0,
        "anticipacion_prom":  round(statistics.mean(anticipaciones), 1) if anticipaciones else None,
    }


def metricas_por_mes(reservas, propiedad_id=None):
    """Agrupa ingresos y noches por mes (YYYY-MM) para gráficos."""
    agrupado = defaultdict(lambda: {"ingreso_bruto":0,"ingreso_neto":0,"noches":0,"reservas":0})
    for r in reservas:
        if propiedad_id and r.get("propiedad_id") != propiedad_id:
            continue
        fi = r.get("fecha_inicio","")
        if not fi or len(fi) < 7:
            continue
        mes = fi[:7]
        agrupado[mes]["ingreso_bruto"] += r.get("ingreso_bruto",0) or 0
        agrupado[mes]["ingreso_neto"]  += r.get("ingreso_neto",0)  or 0
        agrupado[mes]["noches"]        += r.get("noches",0) or 0
        agrupado[mes]["reservas"]      += 1
    return dict(sorted(agrupado.items()))


def comparar_periodos(reservas, fecha_desde, fecha_hasta):
    """
    Compara el período seleccionado con el mes anterior y el mismo período del año pasado.
    Devuelve dict con variaciones porcentuales.
    """
    from dateutil.relativedelta import relativedelta
    d1 = _parse(fecha_desde)
    d2 = _parse(fecha_hasta)
    if not d1 or not d2:
        return {}

    delta = d2 - d1

    # Período anterior (mismo largo, justo antes)
    ant_hasta = d1 - relativedelta(days=1)
    ant_desde = ant_hasta - relativedelta(days=delta.days)

    # Mismo período año anterior
    anio_ant_desde = d1 - relativedelta(years=1)
    anio_ant_hasta = d2 - relativedelta(years=1)

    def met(desde, hasta):
        r = filtrar_reservas(reservas,
                             fecha_desde=desde.isoformat(),
                             fecha_hasta=hasta.isoformat())
        return calcular_metricas(r, desde.isoformat(), hasta.isoformat())

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
        "var_anterior": {
            "ingreso_bruto":   var(actual, anterior, "ingreso_bruto"),
            "tasa_ocupacion":  var(actual, anterior, "tasa_ocupacion"),
            "adr":             var(actual, anterior, "adr"),
        },
        "var_anio_ant": {
            "ingreso_bruto":   var(actual, anio_ant, "ingreso_bruto"),
            "tasa_ocupacion":  var(actual, anio_ant, "tasa_ocupacion"),
            "adr":             var(actual, anio_ant, "adr"),
        },
    }
