# competencia_auto.py
# ### CAMBIO AQUÍ ### — Archivo nuevo: actualización automática de la competencia.
#
#  - Agrupa las propiedades por zona (barrio + ambientes + tipo): una sola búsqueda por grupo.
#  - Guarda los anuncios encontrados para cada propiedad del grupo (tabla competencia).
#  - Guarda una "foto" diaria por propiedad (tabla competencia_historial) para ver la tendencia.
#  - correr_noche() se llama desde /tareas/competencia (un servicio externo como cron-job.org
#    lo llama todas las noches) y procesa los grupos más desactualizados primero.

import json
import os
import threading
from datetime import date, datetime, timedelta, timezone

import database as db
import monedas
import competencia_ia

_lock = threading.Lock()
AR = timezone(timedelta(hours=-3))   # ### CAMBIO AQUÍ ### hora de Buenos Aires (el servidor usa UTC)


def clave_grupo(p):
    return ((p.get("barrio") or "").strip().lower(), p.get("ambientes") or 0, (p.get("tipo") or "").lower())


def agrupar(propiedades):
    grupos = {}
    for p in propiedades:
        if (p.get("estado") or "activa") == "inactiva" or not (p.get("barrio") or "").strip():
            continue
        grupos.setdefault(clave_grupo(p), []).append(p)
    return list(grupos.values())


def guardar_resultado(prop, res, tc):
    """Guarda los comparables, el resumen y la foto del día para UNA propiedad."""
    pid = prop["id"]
    db.execute("DELETE FROM competencia WHERE propiedad_id=%s AND origen='ia'", (pid,))
    db.execute_many("""
        INSERT INTO competencia (propiedad_id,barrio,tipo,ambientes,capacidad,precio_noche,fecha,
                                 fuente,notas,plataforma,titulo,zona,link,rating,origen,moneda)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'ia',%s)
    """, [(
        pid, prop.get("barrio"), prop.get("tipo"),
        c["ambientes"], c["capacidad"], c["precio_noche"], res["fecha"],
        c["link"], c.get("nota", ""), c["plataforma"], c["titulo"], c["zona"], c["link"], c["rating"],
        c["moneda"]
    ) for c in res["comparables"]])

    mon = prop.get("moneda") or "ARS"
    stats = competencia_ia.calcular_stats(res["comparables"], mon, tc)
    resumen = res.get("resumen") or ""
    if not resumen and stats:
        resumen = competencia_ia._resumen_ia(prop, stats)
    valor = json.dumps({"texto": resumen, "fecha": res["fecha"], "fuente": res.get("fuente")},
                       ensure_ascii=False)
    db.execute("""
        INSERT INTO config (clave, valor) VALUES (%s, %s)
        ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor
    """, (f"competencia_resumen_{pid}", valor))

    if stats:
        db.execute("""
            INSERT INTO competencia_historial
              (propiedad_id, fecha, cantidad, mediana, minimo, maximo, moneda, fuente)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (propiedad_id, fecha) DO UPDATE SET
              cantidad=EXCLUDED.cantidad, mediana=EXCLUDED.mediana, minimo=EXCLUDED.minimo,
              maximo=EXCLUDED.maximo, moneda=EXCLUDED.moneda, fuente=EXCLUDED.fuente
        """, (pid, res["fecha"], stats["cantidad"], stats["mediana"], stats["minimo"],
              stats["maximo"], mon, res.get("fuente")))
    return stats


def actualizar_grupo(grupo, tc):
    """Una búsqueda para todo el grupo; se guarda para cada propiedad."""
    res = competencia_ia.buscar_comparables(grupo[0], tc, con_resumen=False)
    if not res["ok"]:
        return res
    for p in grupo:
        guardar_resultado(p, res, tc)
    return res


def _ultima_fecha(grupo):
    ids = [p["id"] for p in grupo]
    row = db.query_one("SELECT MIN(f) AS f FROM (SELECT MAX(fecha) AS f FROM competencia_historial "
                       "WHERE propiedad_id = ANY(%s) GROUP BY propiedad_id) t", (ids,))
    # si alguna propiedad del grupo nunca se actualizó, va primero
    con_hist = db.query_one("SELECT COUNT(DISTINCT propiedad_id) AS n FROM competencia_historial "
                            "WHERE propiedad_id = ANY(%s)", (ids,))["n"]
    if con_hist < len(ids):
        return ""
    return (row or {}).get("f") or ""


def correr_noche():
    """Actualiza los grupos más desactualizados. Guarda un resumen de la corrida en config."""
    if not _lock.acquire(blocking=False):
        return {"ok": False, "mensaje": "Ya hay una actualización en curso."}
    inicio = datetime.now(AR)
    estado = {"inicio": inicio.strftime("%Y-%m-%d %H:%M"), "grupos": 0, "ok": 0,
              "errores": [], "creditos_tavily": 0, "tokens": 0, "terminado": False}
    try:
        tc = monedas.tc_valor()
        props = db.query("SELECT * FROM propiedades ORDER BY id")
        grupos = sorted(agrupar(props), key=_ultima_fecha)
        hoy = datetime.now(AR).date().isoformat()
        maximo = int(os.getenv("MAX_GRUPOS_POR_NOCHE", "10") or 10)
        pendientes = [g for g in grupos if _ultima_fecha(g) != hoy][:maximo]
        estado["grupos"] = len(pendientes)
        for g in pendientes:
            try:
                res = actualizar_grupo(g, tc)
                estado["creditos_tavily"] += res.get("creditos_tavily") or 0
                estado["tokens"] += res.get("tokens") or 0
                if res["ok"]:
                    estado["ok"] += 1
                else:
                    estado["errores"].append(f"{g[0].get('barrio')}: {res['error']}")
            except Exception as e:
                estado["errores"].append(f"{g[0].get('barrio')}: {e}")
    finally:
        estado["terminado"] = True
        estado["fin"] = datetime.now(AR).strftime("%Y-%m-%d %H:%M")
        try:
            db.execute("""
                INSERT INTO config (clave, valor) VALUES ('competencia_ultima_corrida', %s)
                ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor
            """, (json.dumps(estado, ensure_ascii=False),))
        finally:
            _lock.release()
    return estado


def correr_en_segundo_plano():
    """Arranca la corrida sin hacer esperar al que llama (cron-job.org corta a los 30 s)."""
    t = threading.Thread(target=correr_noche, daemon=True)
    t.start()


def ultima_corrida():
    row = db.query_one("SELECT valor FROM config WHERE clave='competencia_ultima_corrida'")
    try:
        return json.loads(row["valor"]) if row else None
    except Exception:
        return None


def historial(pid, dias=30):
    return db.query("""
        SELECT fecha, cantidad, mediana, minimo, maximo, moneda, fuente
        FROM competencia_historial WHERE propiedad_id=%s
        ORDER BY fecha DESC LIMIT %s
    """, (pid, dias))
