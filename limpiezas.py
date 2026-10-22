"""### CAMBIO AQUÍ ### LIMPIEZAS — los recambios de los próximos días, armados con las salidas de huéspedes.

Cada salida es una limpieza. Se juntan:
  · las reservas cargadas (archivo de Airbnb), y
  · el calendario de Airbnb conectado (para reservas nuevas que todavía no están en el archivo).
Si el mismo día entra otro huésped en esa propiedad, la limpieza es urgente (hay que terminar antes del check-in).
"""
from datetime import date, timedelta

import database as db
import metricas as met

DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def _f(d):
    return f"{DIAS[d.weekday()]} {d.day}/{d.month}"


def proximas(hoy=None, dias=14):
    hoy = hoy or date.today()
    fin = hoy + timedelta(days=dias)
    props = {p["id"]: p for p in db.query("SELECT * FROM propiedades WHERE COALESCE(estado,'activa') = 'activa'")}
    salidas, llegadas = {}, {}   # (pid, fecha) -> origen
    for r in db.query("SELECT * FROM reservas WHERE COALESCE(estado,'') <> 'cancelada'"):
        if r["propiedad_id"] not in props:
            continue
        fi, ff, n = met._rango(r)
        if ff and hoy <= ff <= fin:
            salidas[(r["propiedad_id"], ff)] = {"noches": n}
        if fi and hoy <= fi <= fin:
            llegadas[(r["propiedad_id"], fi)] = {"noches": n}
    for b in db.query("SELECT * FROM ical_bloqueos"):
        if b["propiedad_id"] not in props or (b.get("tipo") or "reservada") != "reservada":
            continue
        fi, ff = met._parse(b["desde"]), met._parse(b["hasta"])
        if ff and hoy <= ff <= fin:
            salidas.setdefault((b["propiedad_id"], ff), {"noches": (ff - fi).days if fi else None, "ical": True})
        if fi and hoy <= fi <= fin:
            llegadas.setdefault((b["propiedad_id"], fi), {"noches": None, "ical": True})
    hechas = {x["clave"]: x for x in db.query("SELECT * FROM limpiezas_estado")}
    out = []
    for (pid, d), info in sorted(salidas.items(), key=lambda x: (x[0][1], props[x[0][0]]["nombre"])):
        p = props[pid]
        entra = (pid, d) in llegadas
        prox = min((f for (q, f) in llegadas if q == pid and f >= d), default=None)
        clave = f"{pid}:{d.isoformat()}"
        costo = sum((p.get(k) or 0) for k in ("recambio_limpieza", "recambio_lavanderia", "recambio_insumos"))
        direccion = " ".join(x for x in ((p.get("direccion") or "").strip(), (p.get("piso_depto") or "").strip()) if x)
        msg = (f"Limpieza en {p['nombre']}" + (f" ({direccion})" if direccion else "") + f": {_f(d)}, cuando sale el huésped."
               + (" Entra otro huésped ese mismo día: tiene que quedar lista antes del check-in." if entra
                  else (f" La próxima llegada es el {_f(prox)}." if prox else " No hay otra llegada cargada por ahora.")))
        out.append({"clave": clave, "fecha": d, "fecha_txt": _f(d), "hoy": d == hoy, "manana": d == hoy + timedelta(days=1),
                    "prop": p["nombre"], "pid": pid, "direccion": direccion, "entra_mismo_dia": entra,
                    "proxima": _f(prox) if prox and not entra else None, "costo": costo, "moneda": p.get("moneda") or "ARS",
                    "hecha": clave in hechas and hechas[clave]["estado"] == "hecha",
                    "quien": hechas.get(clave, {}).get("quien", ""), "mensaje": msg, "desde_ical": bool(info.get("ical"))})
    return out
