# novedades.py
# ### CAMBIO AQUÍ ### — Archivo nuevo: historial de cada reserva, calendario y avisos de "hoy / mañana".
#
# Historial: cada vez que se importa un archivo de Airbnb se compara lo que había con lo nuevo y se anota:
#   - "Reserva hecha"   → fecha REAL (columna "Booked" del archivo)
#   - "Cobro de Airbnb" → fecha REAL (columna "Date" del archivo de Ganancias)
#   - "Cancelada", "Cambió fechas", "Cambió el monto" → fecha en que se DETECTÓ (el día que se subió
#     el archivo), porque Airbnb no dice cuándo pasó.

import calendar
from datetime import date, timedelta

import database as db
import metricas
import monedas

ESTADOS = {"confirmada": "Confirmada", "pendiente": "Pendiente", "cancelada": "Cancelada", "completada": "Completada"}


def _f(d):
    d = metricas._parse(d)
    return d.strftime("%d/%m/%Y") if d else "—"


def _guardar(eventos):
    if eventos:
        db.execute_many("""
            INSERT INTO reservas_historial (codigo, propiedad_id, fecha, tipo, detalle, fecha_real)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, eventos)


def antes_de_importar(codigos):
    """Foto de cómo estaban las reservas y los cobros antes de importar."""
    if not codigos:
        return {}, set()
    filas = db.query("SELECT * FROM reservas WHERE codigo_confirmacion = ANY(%s)", (list(codigos),))
    movs = db.query("SELECT codigo, fecha, tipo, bruto, neto, comision, limpieza FROM movimientos_airbnb "
                    "WHERE codigo = ANY(%s)", (list(codigos),))
    return ({f["codigo_confirmacion"]: f for f in filas},
            {_clave_mov(m) for m in movs})


def _clave_mov(m):
    return (m["codigo"], m["fecha"] or "", m["tipo"], *(round(float(m[k] or 0), 2) for k in ("bruto", "neto", "comision", "limpieza")))


def despues_de_importar(antes, movs_antes, filas_archivo, movimientos):
    """Compara y anota las novedades. Devuelve cuántas se registraron."""
    hoy = date.today().isoformat()
    codigos = list({f["codigo_confirmacion"] for f in filas_archivo})
    ahora = {f["codigo_confirmacion"]: f for f in db.query(
        "SELECT * FROM reservas WHERE codigo_confirmacion = ANY(%s)", (codigos,))} if codigos else {}
    ev = []
    for cod, r in ahora.items():
        pid, huesped = r["propiedad_id"], (r.get("huesped_nombre") or "Huésped")
        mon = r.get("moneda") or "ARS"
        prev = antes.get(cod)
        if not prev:
            if r.get("fecha_reserva"):
                ev.append((cod, pid, r["fecha_reserva"], "reservada",
                           f"{huesped} reservó del {_f(r['fecha_inicio'])} al {_f(r['fecha_fin'])}", True))
            else:
                ev.append((cod, pid, hoy, "nueva",
                           f"Se cargó la reserva de {huesped} (del {_f(r['fecha_inicio'])} al {_f(r['fecha_fin'])})", False))
            if r.get("estado") == "cancelada":
                ev.append((cod, pid, hoy, "cancelada", f"{huesped}: figura cancelada en Airbnb", False))
            continue
        if (prev.get("estado") or "") != (r.get("estado") or ""):
            tipo = "cancelada" if r.get("estado") == "cancelada" else "estado"
            ev.append((cod, pid, hoy, tipo,
                       f"{huesped}: pasó de {ESTADOS.get(prev.get('estado'), prev.get('estado') or '—')} "
                       f"a {ESTADOS.get(r.get('estado'), r.get('estado') or '—')}", False))
        if (prev.get("fecha_inicio"), prev.get("fecha_fin")) != (r.get("fecha_inicio"), r.get("fecha_fin")):
            ev.append((cod, pid, hoy, "fechas",
                       f"{huesped}: cambió las fechas, del {_f(prev.get('fecha_inicio'))}–{_f(prev.get('fecha_fin'))} "
                       f"al {_f(r.get('fecha_inicio'))}–{_f(r.get('fecha_fin'))}", False))
        if round(prev.get("ingreso_neto") or 0) != round(r.get("ingreso_neto") or 0) and \
                r.get("estado") != "cancelada" and not any(m["codigo"] == cod for m in movimientos):   # la cancelación ya lo dice
            ev.append((cod, pid, hoy, "monto",
                       f"{huesped}: el monto pasó de {monedas.formatear(prev.get('ingreso_neto') or 0, mon)} "
                       f"a {monedas.formatear(r.get('ingreso_neto') or 0, mon)}", False))
    vistos = set()
    for m in movimientos:   # cobros nuevos (con su fecha real)
        k = _clave_mov(m)
        r = ahora.get(m["codigo"])
        if k in movs_antes or k in vistos or not r:
            continue
        vistos.add(k)
        mon = r.get("moneda") or "ARS"
        nombre = "Ajuste de Airbnb" if m["tipo"] == "ajuste" else "Cobro de Airbnb"
        ev.append((m["codigo"], r["propiedad_id"], m["fecha"] or hoy, "cobro" if m["tipo"] != "ajuste" else "ajuste",
                   f"{nombre}: {monedas.formatear(m['neto'], mon)} ({r.get('huesped_nombre') or 'huésped'})", bool(m["fecha"])))
    _guardar(ev)
    return len(ev)


def historial(codigos):
    """{codigo: [eventos ordenados]}"""
    if not codigos:
        return {}
    out = {}
    for e in db.query("""SELECT * FROM reservas_historial WHERE codigo = ANY(%s)
                         ORDER BY fecha, id""", (list(codigos),)):
        out.setdefault(e["codigo"], []).append(e)
    return out


# ════════════ AVISOS DE HOY / MAÑANA ════════════
def avisos(propiedad_id=None, hoy=None):
    hoy = hoy or date.today()
    manana = hoy + timedelta(days=1)
    reservas = db.query("""
        SELECT r.*, p.nombre AS prop_nombre FROM reservas r LEFT JOIN propiedades p ON p.id = r.propiedad_id
        WHERE COALESCE(r.estado,'') <> 'cancelada' AND (%s::int IS NULL OR r.propiedad_id = %s::int)
    """, (propiedad_id, propiedad_id))
    out = {"hoy_llegan": [], "manana_llegan": [], "hoy_salen": [], "manana_salen": [], "alojados": []}
    for r in reservas:
        fi, ff, _ = metricas._rango(r)
        if not fi:
            continue
        if fi == hoy:
            out["hoy_llegan"].append(r)
        elif fi == manana:
            out["manana_llegan"].append(r)
        if ff == hoy:
            out["hoy_salen"].append(r)
        elif ff == manana:
            out["manana_salen"].append(r)
        if ff and fi < hoy < ff:
            out["alojados"].append(r)
    # novedades de la última semana, solo de reservas que todavía no terminaron
    # (así la primera carga de un año de historial no llena la pantalla de cosas viejas)
    out["recientes"] = db.query("""
        SELECT h.*, p.nombre AS prop_nombre FROM reservas_historial h
        JOIN reservas r ON r.codigo_confirmacion = h.codigo
        LEFT JOIN propiedades p ON p.id = h.propiedad_id
        WHERE ((h.tipo IN ('cancelada', 'fechas', 'monto') AND h.creado_en >= NOW() - INTERVAL '7 days')
               OR (h.tipo = 'reservada' AND h.fecha >= %s))
          AND COALESCE(NULLIF(r.fecha_fin, ''), r.fecha_inicio) >= %s
          AND (%s::int IS NULL OR h.propiedad_id = %s::int)
        ORDER BY h.creado_en DESC, h.id DESC LIMIT 5
    """, ((hoy - timedelta(days=7)).isoformat(), hoy.isoformat(), propiedad_id, propiedad_id))
    out["hay_algo"] = any(out[k] for k in ("hoy_llegan", "manana_llegan", "hoy_salen", "manana_salen", "recientes"))
    return out


def cantidad_hoy():
    """Llegadas + salidas de hoy (para el número del menú)."""
    try:
        a = avisos()
        return len(a["hoy_llegan"]) + len(a["hoy_salen"])
    except Exception:
        return 0


# ════════════ CALENDARIO ════════════
def mes(anio, mes_n, propiedad_id=None):
    """Datos de cada día del mes: llegadas, salidas, alojados, cobros y novedades."""
    d1 = date(anio, mes_n, 1)
    d2 = date(anio, mes_n, calendar.monthrange(anio, mes_n)[1])
    props = db.query("SELECT id, nombre, estado FROM propiedades ORDER BY nombre")
    unidades = len([p for p in props if (not propiedad_id or p["id"] == propiedad_id)
                    and (p.get("estado") or "activa") != "inactiva"]) or 1
    nombres = {p["id"]: p["nombre"] for p in props}
    reservas = [r for r in db.query("SELECT * FROM reservas") if not propiedad_id or r["propiedad_id"] == propiedad_id]
    dias = {}
    d = d1
    while d <= d2:
        dias[d.isoformat()] = {"llegan": [], "salen": [], "alojados": [], "cobros": [], "novedades": [], "canceladas": []}
        d += timedelta(days=1)

    def item(r):
        return {"huesped": r.get("huesped_nombre") or "Huésped", "prop": nombres.get(r["propiedad_id"], ""),
                "desde": _f(r.get("fecha_inicio")), "hasta": _f(r.get("fecha_fin")), "noches": r.get("noches") or 0,
                "monto": monedas.formatear(r.get("ingreso_neto") or 0, r.get("moneda") or "ARS"),
                "estado": ESTADOS.get(r.get("estado"), r.get("estado") or "")}

    for r in reservas:
        fi, ff, _ = metricas._rango(r)
        if not fi:
            continue
        cancelada = (r.get("estado") or "") == "cancelada"
        k = fi.isoformat()
        if k in dias:
            dias[k]["canceladas" if cancelada else "llegan"].append(item(r))
        if cancelada:
            continue
        if ff and ff.isoformat() in dias:
            dias[ff.isoformat()]["salen"].append(item(r))
        if ff:
            x = max(fi, d1)
            while x < ff and x <= d2:
                dias[x.isoformat()]["alojados"].append(item(r))
                x += timedelta(days=1)
    for e in db.query("""SELECT h.*, r.moneda FROM reservas_historial h
                         LEFT JOIN reservas r ON r.codigo_confirmacion = h.codigo
                         WHERE h.fecha >= %s AND h.fecha <= %s
                           AND (%s::int IS NULL OR h.propiedad_id = %s::int)
                         ORDER BY h.id""", (d1.isoformat(), d2.isoformat(), propiedad_id, propiedad_id)):
        k = (e["fecha"] or "")[:10]
        if k in dias:
            dest = "cobros" if e["tipo"] in ("cobro", "ajuste") else "novedades"
            dias[k][dest].append({"detalle": e["detalle"], "real": bool(e["fecha_real"]),
                                  "prop": nombres.get(e["propiedad_id"], ""), "tipo": e["tipo"]})
    for k, v in dias.items():
        v["ocupacion"] = round(min(len(v["alojados"]) / unidades, 1) * 100)
    return dias, unidades
