# pruebas.py
# ### CAMBIO AQUÍ ### — Archivo nuevo: pruebas que Adriano hace en Airbnb, su resultado y lo que aprende el sistema.
#
# Cómo funciona, en simple:
#   1) Se anota qué se cambió en Airbnb (a mano, o solo al tocar "✓ Hecho" en Qué hacer hoy).
#      Para un precio se guarda también cuánto sugería el sistema ese día (sin el ajuste aprendido).
#   2) Con las reservas y el calendario se ve qué pasó:
#        precio → ¿se vendieron esas noches?, ¿con cuánta anticipación comparado con lo normal?
#        descuentos, promociones, estadía mínima → reservas hechas 14 días antes vs 14 días después.
#   3) Veredicto: 🟢 funcionó · 🟡 a medias / en el límite · 🔴 no funcionó · ⚪ todavía no se sabe.
#   4) Aprendizaje: si la gente paga más (o menos) de lo que sugería el sistema, se calcula un ajuste
#      por propiedad que se aplica solo a los precios sugeridos. Con menos de 3 pruebas se aplica la mitad.
#      Se puede apagar ("deshacer") por propiedad.
# No es magia: son cuentas simples y siempre se muestra el porqué.

import statistics
from datetime import date, timedelta

import database as db
import disposicion_pago as dp
import ical
import metricas
import monedas

TIPOS = {
    "precio": ("Puse un precio por noche", "$"),
    "descuento": ("Puse un descuento", "%"),
    "saque_descuento": ("Saqué un descuento", "%"),
    "promocion": ("Activé una promoción de Airbnb", "%"),
    "saque_promocion": ("Saqué una promoción de Airbnb", "%"),
    "minima": ("Cambié la estadía mínima", "noches"),
    "otro": ("Otro cambio", ""),
}
# nombres de las pruebas anotadas antes de esta versión (se siguen mostrando)
VIEJOS = {"promo": "Promoción personalizada", "semanal": "Descuento semanal", "mensual": "Descuento mensual",
          "anticipada": "Descuento por reserva anticipada", "ultimo_momento": "Descuento de último momento",
          "minima": "Cambio de estadía mínima"}
VENTANA = 14
MAX_NOCHES = 60
LIMITES = (0.85, 1.25)


def nombre_tipo(t):
    return TIPOS[t][0] if t in TIPOS else VIEJOS.get(t, t or "Cambio")


def _f(d):
    return d.strftime("%d/%m") if d else "—"


def _fmt(v, mon):
    return monedas.formatear(v, mon)


def _reservas_prop(pid, tc, mon):
    propias = db.query("SELECT * FROM reservas WHERE propiedad_id=%s", (pid,))
    conv, _ = monedas.convertir_reservas(propias, mon, tc)
    return dp._validas(conv)


def _evaluar_precio(p, validas, med_ant, hoy, pid):
    mon = p["_mon"]
    f = metricas._parse(p["fecha"])
    d1, d2 = metricas._parse(p.get("desde")), metricas._parse(p.get("hasta"))
    if not d1 or not d2 or d2 < d1 or not p.get("valor"):
        return {"color": "⚪", "codigo": "sin_datos", "texto": "Faltan las fechas o el precio de la prueba.", "detalle": []}
    d2 = min(d2, d1 + timedelta(days=MAX_NOCHES - 1))
    noches = [d1 + timedelta(days=k) for k in range((d2 - d1).days + 1)]
    cal = ical.noches_ocupadas(pid, d1, d2 + timedelta(days=1)) if p.get("_ical") else set()
    antes, vendidas, leads, precios = 0, 0, [], []
    for n in noches:
        r = next((v for v in validas if v["fi"] <= n < v["ff"]), None)
        if r and r["fr"] and f and r["fr"] < f:
            antes += 1                      # ya estaba vendida antes del cambio: no cuenta
            continue
        if r:
            vendidas += 1
            if r["ant"] is not None:
                leads.append(r["ant"])
            if r["precio"]:
                precios.append(r["precio"])
        elif n in cal:
            vendidas += 1                   # ocupada según el calendario (todavía sin archivo de Reservas)
    total = len(noches) - antes
    detalle = [f"Noches de la prueba: {_f(d1)} al {_f(d2)} ({len(noches)}).",
               f"Precio puesto: {_fmt(p['valor'], mon)}"
               + (f"; el sistema sugería {_fmt(p['sugerido'], mon)}." if p.get("sugerido") else ".")]
    if antes:
        detalle.append(f"{antes} noche(s) ya estaban vendidas antes del cambio y no se cuentan.")
    if total <= 0:
        return {"color": "⚪", "codigo": "sin_datos", "texto": "Esas noches ya estaban vendidas antes del cambio.", "detalle": detalle}
    detalle.append(f"Vendidas después del cambio: {vendidas} de {total}.")
    if precios:
        detalle.append(f"Te pagaron en promedio {_fmt(statistics.mean(precios), mon)} por noche (sin limpieza).")
    lead = statistics.median(leads) if leads else None
    if lead is not None and med_ant is not None:
        detalle.append(f"Se reservaron {lead:g} días antes; lo normal en tus reservas es {med_ant} días.")
    terminada = all(n < hoy for n in noches)
    if vendidas < total and not terminada:
        faltan = (d1 - hoy).days
        return {"color": "⚪", "codigo": "esperando",
                "texto": (f"Esperando: vendidas {vendidas} de {total} noches"
                          + (f", faltan {faltan} días." if faltan > 0 else ".")), "detalle": detalle}
    ratio = vendidas / total
    v = _fmt(p["valor"], mon)
    if ratio >= 0.7:
        if lead is not None and med_ant is not None and lead >= max(med_ant * 1.3, med_ant + 7):
            return {"color": "🟢", "codigo": "rapido", "texto": f"Se vendió rápido a {v}: podías cobrar más.", "detalle": detalle}
        if lead is not None and med_ant is not None and lead <= max(med_ant * 0.4, 2):
            return {"color": "🟡", "codigo": "limite", "texto": f"Se vendió a último momento: {v} es el límite.", "detalle": detalle}
        return {"color": "🟢", "codigo": "ok", "texto": f"Funcionó: se vendió a {v}.", "detalle": detalle}
    if ratio >= 0.3:
        return {"color": "🟡", "codigo": "medias", "texto": f"A medias: se vendieron {vendidas} de {total} noches a {v}.", "detalle": detalle}
    if p.get("sugerido") and p["valor"] <= p["sugerido"]:
        return {"color": "🔴", "codigo": "no", "texto": f"Ni a {v} se vendió: el problema no parece ser el precio.", "detalle": detalle}
    return {"color": "🔴", "codigo": "no", "texto": f"No se vendió a {v}: era mucho.", "detalle": detalle}


def _evaluar_ventana(p, validas, hoy):
    f = metricas._parse(p["fecha"])
    if not f:
        return {"color": "⚪", "codigo": "sin_datos", "texto": "Falta la fecha del cambio.", "detalle": []}

    def resumen(a, b):
        g = [v for v in validas if v["fr"] and a <= v["fr"] < b]
        return len(g), sum(v["n"] for v in g)
    ra, na = resumen(f - timedelta(days=VENTANA), f)
    rd, nd = resumen(f, min(f + timedelta(days=VENTANA), hoy + timedelta(days=1)))
    faltan = (f + timedelta(days=VENTANA) - hoy).days
    detalle = [f"Reservas hechas los {VENTANA} días antes del cambio: {ra} ({na} noches).",
               f"Reservas hechas los {VENTANA} días después: {rd} ({nd} noches)" + (f" — faltan {faltan} días." if faltan > 0 else ".")]
    if faltan > 0:
        return {"color": "⚪", "codigo": "esperando", "texto": f"Esperando: faltan {faltan} días para comparar.", "detalle": detalle}
    if ra == 0 and rd == 0:
        return {"color": "⚪", "codigo": "sin_datos", "texto": "No hubo reservas ni antes ni después: no se puede comparar.", "detalle": detalle}
    t = p["tipo"]
    if t in ("descuento", "promocion"):
        if rd > ra:
            return {"color": "🟢", "codigo": "ok", "texto": f"Trajo más reservas ({ra} → {rd}).", "detalle": detalle}
        return {"color": "🔴", "codigo": "no", "texto": f"No trajo más reservas ({ra} → {rd}): no vale el descuento.", "detalle": detalle}
    if t in ("saque_descuento", "saque_promocion"):
        if rd >= ra * 0.8:
            return {"color": "🟢", "codigo": "ok", "texto": f"Se siguió alquilando ({ra} → {rd}): no hacía falta.", "detalle": detalle}
        return {"color": "🔴", "codigo": "no", "texto": f"Bajaron las reservas ({ra} → {rd}): ayudaba.", "detalle": detalle}
    if t == "minima":
        if nd >= na:
            return {"color": "🟢", "codigo": "ok", "texto": f"Se vendieron igual o más noches ({na} → {nd}).", "detalle": detalle}
        return {"color": "🔴", "codigo": "no", "texto": f"Se vendieron menos noches ({na} → {nd}).", "detalle": detalle}
    return {"color": "⚪", "codigo": "info", "texto": f"Reservas antes {ra}, después {rd}.", "detalle": detalle}


def evaluar_todas(hoy=None, tc=None):
    """Lista de pruebas (todas las propiedades) con su resultado, más reciente primero."""
    hoy = hoy or date.today()
    props = {p["id"]: p for p in db.query("SELECT * FROM propiedades")}
    filas = db.query("SELECT * FROM pruebas_descuento ORDER BY fecha DESC, id DESC LIMIT 300")
    cache = {}
    out = []
    for p in filas:
        prop = props.get(p["propiedad_id"])
        if not prop:
            continue
        mon = prop.get("moneda") or "ARS"
        if prop["id"] not in cache:
            validas = _reservas_prop(prop["id"], tc, mon)
            ants = [v["ant"] for v in validas if v["ant"] is not None]
            cache[prop["id"]] = (validas, round(statistics.median(ants)) if len(ants) >= dp.MIN_RESERVAS else None)
        validas, med_ant = cache[prop["id"]]
        p = dict(p, _mon=mon, _ical=bool((prop.get("ical_url") or "").strip()), prop=prop["nombre"])
        if p["tipo"] == "precio":
            res = _evaluar_precio(p, validas, med_ant, hoy, prop["id"])
        else:
            res = _evaluar_ventana(p, validas, hoy)
        unidad = TIPOS.get(p["tipo"], ("", ""))[1]
        if p.get("valor") is None and p.get("porcentaje"):
            p["valor"], unidad = p["porcentaje"], "%"
        if p.get("valor"):
            valor_txt = (_fmt(p["valor"], mon) if unidad == "$" else
                         f"{p['valor']:g}%" if unidad == "%" else f"{p['valor']:g} noches" if unidad == "noches" else f"{p['valor']:g}")
        else:
            valor_txt = ""
        fechas = ""
        if p.get("desde"):
            d1, d2 = metricas._parse(p["desde"]), metricas._parse(p.get("hasta") or p["desde"])
            fechas = _f(d1) if d1 == d2 else f"{_f(d1)} al {_f(d2)}"
        out.append({**p, **res, "que": nombre_tipo(p["tipo"]), "valor_txt": valor_txt, "fechas": fechas})
    return out


# ═══════════════ APRENDIZAJE ═══════════════
PESO = {"rapido": 1.05, "ok": 1.0, "limite": 0.98, "medias": 0.92}


def _evidencia(p):
    """Qué dice una prueba de precio sobre cuánto paga la gente comparado con la sugerencia (1.0 = igual)."""
    r = p["valor"] / p["sugerido"]
    if p["codigo"] in PESO:
        return r * PESO[p["codigo"]]
    if p["codigo"] == "no" and r > 1:
        return 0.97          # subió y no se vendió: el sistema no se quedaba corto, más bien un poco alto
    return None              # no se vendió ni con precio bajo: no dice nada del precio


def aprendizaje(pid, evaluadas):
    """Ajuste de precio aprendido para una propiedad: {'factor', 'n', 'texto', 'activo'} o None."""
    evid = [e for e in (_evidencia(p) for p in evaluadas
                        if p["propiedad_id"] == pid and p["tipo"] == "precio" and p.get("valor") and p.get("sugerido"))
            if e is not None]
    if not evid:
        return None
    estimado = max(LIMITES[0], min(LIMITES[1], statistics.median(evid)))
    n = len(evid)
    factor = estimado if n >= 3 else 1 + (estimado - 1) / 2
    if abs(factor - 1) < 0.02:
        return {"factor": 1.0, "n": n, "activo": False,
                "texto": f"Tus {n} prueba(s) de precio coinciden con lo que sugiere el sistema: no hace falta ajustar."}
    apagado = db.query_one("SELECT valor FROM config WHERE clave=%s", (f"aprendizaje_off_{pid}",))
    pct = round((factor - 1) * 100)
    texto = (f"La gente paga {abs(round((estimado - 1) * 100))}% {'más' if estimado > 1 else 'menos'} de lo que sugería el sistema "
             f"({n} prueba{'s' if n > 1 else ''} de precio). "
             + (f"Ajuste aplicado: {'+' if pct > 0 else ''}{pct}%" + (" (a medias: con menos de 3 pruebas se ajusta la mitad)." if n < 3 else ".")))
    return {"factor": factor, "n": n, "activo": not apagado, "texto": texto, "pct": pct}


def factor_precio(pid, tc=None, evaluadas=None):
    """El ajuste que usan los precios sugeridos (1.0 si no hay o si está apagado)."""
    try:
        a = aprendizaje(pid, evaluadas if evaluadas is not None else evaluar_todas(tc=tc))
    except Exception as e:
        print(f"[pruebas] aprendizaje {pid}: {e}")
        return 1.0, None
    if not a or not a["activo"]:
        return 1.0, a
    return a["factor"], a


def lecciones(pid, evaluadas):
    """Frases cortas de lo que funcionó y lo que no, por tipo de cambio (sin contar las de precio)."""
    grupos = {}
    for p in evaluadas:
        if p["propiedad_id"] != pid or p["tipo"] == "precio" or p["codigo"] not in ("ok", "no"):
            continue
        g = grupos.setdefault(p["tipo"], [0, 0])
        g[0 if p["codigo"] == "ok" else 1] += 1
    out = []
    frases = {"descuento": ("Poner descuento", "trajo más reservas"), "promocion": ("Las promociones", "trajeron más reservas"),
              "saque_descuento": ("Sacar el descuento", "no bajó las reservas"),
              "saque_promocion": ("Sacar la promoción", "no bajó las reservas"),
              "minima": ("Cambiar la estadía mínima", "mantuvo o subió las noches vendidas")}
    for t, (bien, mal) in grupos.items():
        if t not in frases:
            continue
        quien, que = frases[t]
        total = bien + mal
        color = "🟢" if bien > mal else ("🔴" if mal > bien else "🟡")
        out.append(f"{color} {quien} {que} en {bien} de {total} prueba{'s' if total > 1 else ''}.")
    return out


def superpuesta(pid, tipo, fecha, desde, hasta):
    """¿Hay otra prueba de la misma propiedad que se mezcle con esta?"""
    for p in db.query("SELECT * FROM pruebas_descuento WHERE propiedad_id=%s", (pid,)):
        f = metricas._parse(p["fecha"])
        if tipo == "precio" and p["tipo"] == "precio" and desde and p.get("desde"):
            if metricas._parse(p["desde"]) <= hasta and desde <= metricas._parse(p.get("hasta") or p["desde"]):
                return p
        elif f and abs((f - fecha).days) < VENTANA and (tipo != "precio" or p["tipo"] != "precio"):
            return p
    return None
