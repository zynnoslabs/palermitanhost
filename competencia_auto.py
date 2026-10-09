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


CLAVE_BLOQUEO = 515151   # ### CAMBIO AQUÍ ### candado en la base para no correr dos búsquedas a la vez


def clave_grupo(p):
    # ### CAMBIO AQUÍ ### ciudad + barrio + ambientes: la búsqueda filtra por dormitorios y capacidad,
    # así un monoambiente y un 4 ambientes del mismo barrio ya no comparten los mismos precios.
    return ((p.get("ciudad") or "").strip().lower(), (p.get("barrio") or "").strip().lower(),
            int(p.get("ambientes") or 0))


def agrupar(propiedades):
    grupos = {}
    for p in propiedades:
        if (p.get("estado") or "activa") == "inactiva" or not (p.get("barrio") or "").strip():
            continue
        grupos.setdefault(clave_grupo(p), []).append(p)
    return list(grupos.values())


DIAS_VIGENCIA = competencia_ia._env_int("COMPETENCIA_DIAS", 30)   # ### CAMBIO AQUÍ ### "30 días" ya no rompe el arranque


def comparables_vigentes(pid, barrio):
    """### CAMBIO AQUÍ ### Precios que cuentan para la referencia de la zona:
    los que encontró la IA en los últimos DIAS_VIGENCIA días + los cargados a mano."""
    desde = (datetime.now(AR).date() - timedelta(days=DIAS_VIGENCIA)).isoformat()
    return db.query("""
        SELECT * FROM competencia
        WHERE (propiedad_id=%s OR (propiedad_id IS NULL AND barrio=%s))
          AND precio_noche > 0
          AND (COALESCE(origen,'manual') <> 'ia' OR COALESCE(fecha,'') >= %s)
        ORDER BY precio_noche
    """, (pid, barrio, desde))


def guardar_resultado(prop, res, tc):
    """Guarda los comparables, el resumen y la foto del día para UNA propiedad.
    ### CAMBIO AQUÍ ### Ya no borra lo anterior: los precios se ACUMULAN día a día
    (se borran solo los de más de DIAS_VIGENCIA días, y si un anuncio vuelve a aparecer
    se reemplaza por el precio nuevo, así no se cuenta dos veces)."""
    pid = prop["id"]
    desde = (datetime.now(AR).date() - timedelta(days=DIAS_VIGENCIA)).isoformat()
    db.execute("DELETE FROM competencia WHERE propiedad_id=%s AND origen='ia' AND COALESCE(fecha,'') < %s",
               (pid, desde))
    links = [c["link"] for c in res["comparables"] if c.get("link")]
    if links:
        db.execute("DELETE FROM competencia WHERE propiedad_id=%s AND origen='ia' AND link = ANY(%s)",
                   (pid, links))
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
    # ### CAMBIO AQUÍ ### la referencia se calcula con TODO lo acumulado (IA 30 días + manual)
    stats = competencia_ia.calcular_stats(comparables_vigentes(pid, prop.get("barrio")), mon, tc)
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


def actualizar_grupo(grupo, tc, max_paginas=None):
    """Una búsqueda para todo el grupo; se guarda para cada propiedad."""
    res = competencia_ia.buscar_comparables(grupo[0], tc, con_resumen=False, max_paginas_serpapi=max_paginas)
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


def _guardar_estado(estado):
    db.execute("""
        INSERT INTO config (clave, valor) VALUES ('competencia_ultima_corrida', %s)
        ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor
    """, (json.dumps(estado, ensure_ascii=False),))


def presupuesto_serpapi(restantes, hoy=None):
    """### CAMBIO AQUÍ ### búsquedas de Google que se pueden usar esta noche sin quedarse sin cupo
    antes de fin de mes: lo que queda ÷ noches que faltan (incluida hoy)."""
    if restantes is None:
        return None
    import calendar
    hoy = hoy or datetime.now(AR).date()
    noches = calendar.monthrange(hoy.year, hoy.month)[1] - hoy.day + 1
    return max(int(restantes) // max(noches, 1), 0)


def correr_noche():
    """Actualiza los grupos más desactualizados. Guarda un resumen de la corrida en config."""
    if not _lock.acquire(blocking=False):
        return {"ok": False, "mensaje": "Ya hay una actualización en curso."}
    try:
        with db.bloqueo(CLAVE_BLOQUEO) as obtenido:
            if not obtenido:   # la está corriendo el otro proceso de Render
                return {"ok": False, "mensaje": "Ya hay una actualización en curso."}
            return _correr_noche()
    finally:
        _lock.release()


def _correr_noche():
    inicio = datetime.now(AR)
    estado = {"inicio": inicio.strftime("%Y-%m-%d %H:%M"), "grupos": 0, "ok": 0,
              "errores": [], "creditos_tavily": 0, "tokens": 0, "terminado": False,
              "busquedas_serpapi": 0, "serpapi_restantes": None}   # ### CAMBIO AQUÍ ###
    try:
        tc = monedas.tc_valor()
        props = db.query("SELECT * FROM propiedades ORDER BY id")
        grupos = sorted(agrupar(props), key=_ultima_fecha)
        hoy = datetime.now(AR).date().isoformat()
        maximo = competencia_ia._env_int("MAX_GRUPOS_POR_NOCHE", 10)
        pendientes = [g for g in grupos if _ultima_fecha(g) != hoy][:maximo]
        estado["grupos"] = len(pendientes)
        _guardar_estado(estado)   # ### CAMBIO AQUÍ ### queda "en curso" aunque Render corte a la mitad
        serp_key = os.getenv("SERPAPI_API_KEY")
        cupo = presupuesto_serpapi(competencia_ia.serpapi_busquedas_restantes(serp_key)) if serp_key else None
        for i, g in enumerate(pendientes):
            # ### CAMBIO AQUÍ ### reparte el cupo del mes: 2 páginas solo si sobra para los grupos que faltan
            paginas = None
            if cupo is not None:
                faltan = len(pendientes) - i
                paginas = 0 if cupo <= 0 else (2 if cupo >= faltan + 1 else 1)
            try:
                res = actualizar_grupo(g, tc, paginas)
                if cupo is not None:
                    cupo -= res.get("busquedas_serpapi") or 0
                estado["creditos_tavily"] += res.get("creditos_tavily") or 0
                estado["tokens"] += res.get("tokens") or 0
                estado["busquedas_serpapi"] += res.get("busquedas_serpapi") or 0   # ### CAMBIO AQUÍ ###
                if res["ok"]:
                    estado["ok"] += 1
                    for a in res.get("avisos") or []:   # una fuente falló pero otra la reemplazó
                        estado["errores"].append(f"{g[0].get('barrio')} (se usó otra fuente): {a}")
                else:
                    estado["errores"].append(f"{g[0].get('barrio')}: {res['error']}")
            except Exception as e:
                estado["errores"].append(f"{g[0].get('barrio')}: {competencia_ia.limpiar_error(e)}")
        if os.getenv("SERPAPI_API_KEY"):   # ### CAMBIO AQUÍ ### consulta gratis, no gasta búsquedas
            estado["serpapi_restantes"] = competencia_ia.serpapi_busquedas_restantes(os.getenv("SERPAPI_API_KEY"))
    finally:
        estado["terminado"] = True
        estado["fin"] = datetime.now(AR).strftime("%Y-%m-%d %H:%M")
        try:
            _guardar_estado(estado)
        except Exception:
            pass
    return estado


def en_curso():
    """### CAMBIO AQUÍ ### True si la búsqueda automática está corriendo ahora (en cualquier proceso)."""
    try:
        return db.esta_bloqueado(CLAVE_BLOQUEO)
    except Exception:
        return False


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


# ### CAMBIO AQUÍ ### aviso en el dashboard si la búsqueda automática no trae datos hace varios días
DIAS_ALERTA = 3


def alerta_sin_datos():
    if not os.getenv("TAREAS_TOKEN"):
        return None
    corrida = ultima_corrida()
    if not corrida:
        return None
    n = db.query_one("""SELECT COUNT(*) AS n FROM propiedades
                        WHERE COALESCE(estado,'activa') <> 'inactiva' AND COALESCE(TRIM(barrio),'') <> ''""")["n"]
    if not n:
        return None
    row = db.query_one("SELECT MAX(fecha) AS f FROM competencia_historial")
    ultima = row["f"] if row else None
    dias = None
    if ultima:
        try:
            dias = (datetime.now(AR).date() - date.fromisoformat(str(ultima)[:10])).days
        except ValueError:
            dias = None
        if dias is not None and dias < DIAS_ALERTA:
            return None
    return {"dias": dias, "ultima": ultima, "errores": (corrida.get("errores") or [])[:3]}


def historial(pid, dias=30):
    return db.query("""
        SELECT fecha, cantidad, mediana, minimo, maximo, moneda, fuente
        FROM competencia_historial WHERE propiedad_id=%s
        ORDER BY fecha DESC LIMIT %s
    """, (pid, dias))
