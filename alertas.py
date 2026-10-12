# alertas.py
# ### CAMBIO AQUÍ ### — Archivo nuevo: revisa el sistema y avisa de situaciones raras o pendientes.
# Cada alerta: {"nivel": "alta"|"media"|"info", "titulo", "detalle", "link"}.
# "alta" = algo está mal (datos que se pisan, plata que no cierra).
# "media" = algo para hacer (archivos viejos, reseñas sin responder, datos incompletos).
# "info" = oportunidades (noches libres, precio lejos del mercado).

import hashlib
import json
from datetime import date, timedelta, datetime

import database as db
import metricas
import monedas
import disposicion_pago   # ### CAMBIO AQUÍ ###

ORDEN = {"alta": 0, "media": 1, "info": 2}
DIAS_OCULTA = 7   # ### CAMBIO AQUÍ ### una alerta ocultada vuelve a aparecer después de esto (si sigue pasando)


def _f(d):
    d = metricas._parse(d)
    return d.strftime("%d/%m") if d else "—"


def superposiciones(reservas, nombres):
    """Pares de reservas (no canceladas) de la MISMA propiedad que comparten noches."""
    por_prop = {}
    for r in reservas:
        if (r.get("estado") or "") == "cancelada":
            continue
        fi, ff, _ = metricas._rango(r)
        if fi and ff:
            por_prop.setdefault(r["propiedad_id"], []).append((fi, ff, r))
    out = []
    for pid, lista in por_prop.items():
        lista.sort(key=lambda x: x[0])
        for i, (fi, ff, r) in enumerate(lista):
            for fj, fj2, s in lista[i + 1:]:
                if fj >= ff:
                    break
                desde, hasta = max(fi, fj), min(ff, fj2)
                out.append({"prop": nombres.get(pid, "?"), "a": r, "b": s, "desde": desde, "hasta": hasta})
    return out


def revisar(propiedad_id=None, hoy=None):
    hoy = hoy or date.today()
    props = db.query("SELECT * FROM propiedades ORDER BY nombre")
    if propiedad_id:
        props = [p for p in props if p["id"] == propiedad_id]
    nombres = {p["id"]: p["nombre"] for p in props}
    reservas = [r for r in db.query("SELECT * FROM reservas") if r["propiedad_id"] in nombres]
    al = []

    def add(nivel, titulo, detalle, link=""):
        al.append({"nivel": nivel, "titulo": titulo, "detalle": detalle, "link": link})

    # 1) Reservas que se pisan en la misma propiedad
    for s in superposiciones(reservas, nombres):
        if s["hasta"] < hoy - timedelta(days=60):
            continue   # cosas muy viejas no se muestran
        noches = (s["hasta"] - s["desde"]).days
        add("alta", "Reservas superpuestas",
            f"En {s['prop']}, {s['a'].get('huesped_nombre') or 'un huésped'} y {s['b'].get('huesped_nombre') or 'otro huésped'} "
            f"comparten {noches} noche(s) ({_f(s['desde'])} al {_f(s['hasta'])}). Puede ser un anuncio asignado a la propiedad "
            f"equivocada al importar, o una doble reserva.", f"calendario?mes={s['desde']:%Y-%m}&dia={s['desde'].isoformat()}&resaltar=dia-{s['desde'].isoformat()}")

    # 2) Reserva confirmada en una propiedad inactiva o en mantenimiento
    estado_prop = {p["id"]: (p.get("estado") or "activa") for p in props}
    for r in reservas:
        fi, ff, _ = metricas._rango(r)
        if fi and ff and ff >= hoy and (r.get("estado") or "") != "cancelada" and estado_prop.get(r["propiedad_id"]) != "activa":
            add("alta", "Reserva en propiedad fuera de servicio",
                f"{r.get('huesped_nombre') or 'Un huésped'} llega el {_f(fi)} a {nombres[r['propiedad_id']]}, "
                f"que figura como {estado_prop[r['propiedad_id']]}.", f"propiedades/{r['propiedad_id']}/editar?resaltar=estado")

    # 3) Solicitudes pendientes que llegan pronto
    for r in reservas:
        fi, _, _ = metricas._rango(r)
        if fi and (r.get("estado") or "") == "pendiente" and hoy <= fi <= hoy + timedelta(days=3):
            add("alta", "Solicitud sin confirmar",
                f"{r.get('huesped_nombre') or 'Un huésped'} llega el {_f(fi)} a {nombres[r['propiedad_id']]} y la reserva "
                f"sigue pendiente. Revisalo en Airbnb.", f"calendario?mes={fi:%Y-%m}&dia={fi.isoformat()}&resaltar=dia-{fi.isoformat()}")

    # 4) Estadías que ya terminaron y no tienen el cobro cargado (si alguna vez se subió Ganancias)
    ganancias = db.query_one("SELECT valor FROM config WHERE clave='ultima_importacion_ganancias'")
    if ganancias and ganancias["valor"]:
        cobrados = {m["codigo"] for m in db.query("SELECT DISTINCT codigo FROM movimientos_airbnb")}
        sin_cobro = [r for r in reservas
                     if (r.get("estado") or "") != "cancelada" and r["codigo_confirmacion"] not in cobrados
                     and (metricas._rango(r)[1] or hoy) < hoy - timedelta(days=7)
                     and (metricas._rango(r)[1] or hoy) >= hoy - timedelta(days=90)]
        if sin_cobro:
            ej = ", ".join((r.get("huesped_nombre") or "?") for r in sin_cobro[:3])
            add("media", "Estadías terminadas sin el cobro cargado",
                f"{len(sin_cobro)} reserva(s) ya terminaron hace más de una semana y no figuran en el archivo de Ganancias "
                f"({ej}{'…' if len(sin_cobro) > 3 else ''}). Subí el archivo de Ganancias actualizado.", "importar?resaltar=subir-ganancias")

    # 5) Archivos de Airbnb viejos
    if reservas:
        for tipo, dias, nombre in (("reservas", 7, "Reservas"), ("ganancias", 31, "Ganancias")):
            row = db.query_one("SELECT valor FROM config WHERE clave=%s", (f"ultima_importacion_{tipo}",))
            ultima = metricas.fecha_valida(row["valor"]) if row and row["valor"] else None
            if not ultima:
                add("media", f"Nunca se subió el archivo de {nombre}",
                    f"Subilo en Importar CSV para que {'aparezcan las reservas futuras y cancelaciones' if tipo == 'reservas' else 'los montos sean exactos'}.",
                    f"importar?resaltar=subir-{tipo}")   # ### CAMBIO AQUÍ ### se ilumina su renglón
            elif (hoy - ultima).days > dias:
                add("media", f"El archivo de {nombre} tiene {(hoy - ultima).days} días",
                    f"Lo ideal es subirlo {'una vez por semana' if tipo == 'reservas' else 'una vez por mes'}. "
                    f"Hasta entonces pueden faltar reservas nuevas o cancelaciones.", f"importar?resaltar=subir-{tipo}")

    # 6) Propiedades con datos incompletos
    for p in props:
        if (p.get("estado") or "activa") == "inactiva":
            continue
        campos = {"barrio": "barrio", "precio base": "precio_base",
                  "costos fijos": "costo_expensas,costo_servicios,costo_limpieza,costo_comision"}
        faltan = [n for n, ok in (("barrio", (p.get("barrio") or "").strip()), ("precio base", p.get("precio_base")),
                                  ("costos fijos", any(p.get(k) for k in ("costo_expensas", "costo_servicios", "costo_limpieza", "costo_comision"))))
                  if not ok]
        if faltan:
            add("media", f"Faltan datos de {p['nombre']}",
                f"Completá: {', '.join(faltan)}. " + ("Sin barrio no se busca la competencia. " if "barrio" in faltan else "")
                + ("Sin costos, el ingreso neto real sale más alto de lo que es." if "costos fijos" in faltan else ""),
                f"propiedades/{p['id']}/editar?resaltar=" + ",".join(campos[x] for x in faltan))

    # 7) Reseñas y consultas sin responder hace más de una semana
    q = db.query_one("""SELECT COUNT(*) n FROM resenas WHERE pendiente = 1 AND creada_en < NOW() - INTERVAL '7 days'
                        AND (%s::int IS NULL OR propiedad_id = %s::int)""", (propiedad_id, propiedad_id))["n"]
    if q:
        add("media", f"{q} reseña(s) sin responder hace más de una semana",
            "Responder las reseñas ayuda a mantener el puntaje y la confianza de los próximos huéspedes.", "asistente?tab=resenas&resaltar=resenas-pendientes")
    q = db.query_one("""SELECT COUNT(*) n FROM consultas_huespedes WHERE pendiente = 1 AND creada_en < NOW() - INTERVAL '2 days'
                        AND (%s::int IS NULL OR propiedad_id = %s::int)""", (propiedad_id, propiedad_id))["n"]
    if q:
        add("media", f"{q} consulta(s) de huéspedes pendientes", "Hay consultas marcadas como pendientes hace más de 2 días.",
            "asistente?tab=huespedes&resaltar=consultas-pendientes")

    # 8) Tipo de cambio viejo cuando hay cosas en dólares
    hay_usd = any((p.get("moneda") or "ARS") == "USD" for p in props) or any((r.get("moneda") or "ARS") == "USD" for r in reservas)
    tc = monedas.get_tc()
    if hay_usd:
        f_tc = metricas.fecha_valida((tc or {}).get("fecha")) if tc else None
        if not tc:
            add("media", "Falta el tipo de cambio", "Hay montos o costos en dólares que no se están sumando con los pesos. Cargalo arriba a la derecha.", "?resaltar=tc")
        elif f_tc and (hoy - f_tc).days > 7:
            add("media", f"El tipo de cambio tiene {(hoy - f_tc).days} días",
                "Actualizalo arriba a la derecha para que las conversiones entre pesos y dólares sean correctas.", "?resaltar=tc")

    # ### CAMBIO AQUÍ ### 8b) Se está vendiendo más rápido de lo normal → se puede cobrar más
    for p in props:
        if (p.get("estado") or "activa") != "activa":
            continue
        try:
            f = disposicion_pago.oportunidad(p, reservas, hoy, monedas.tc_valor())
        except Exception:
            f = None
        if f:
            add("info", f"{p['nombre']}: se está vendiendo más rápido de lo normal",
                f"{f['nombre']}: ya vendiste {f['real']}% de las noches; lo normal a esta altura es {f['esperado']}%. "
                f"Podés subir el precio de las noches libres.", f"precios?propiedad_id={p['id']}&resaltar=ritmo")

    # 9) Muchas noches libres en las próximas 2 semanas (oportunidad de bajar precio o promocionar)
    for p in props:
        if (p.get("estado") or "activa") != "activa":
            continue
        ocupadas = set()
        for r in reservas:
            if r["propiedad_id"] != p["id"] or (r.get("estado") or "") == "cancelada":
                continue
            fi, ff, _ = metricas._rango(r)
            if fi and ff:
                d = max(fi, hoy)
                while d < ff and d < hoy + timedelta(days=14):
                    ocupadas.add(d)
                    d += timedelta(days=1)
        libres = 14 - len(ocupadas)
        if libres >= 7 and any(r["propiedad_id"] == p["id"] for r in reservas):
            add("info", f"{p['nombre']}: {libres} noches libres en las próximas 2 semanas",
                "Puede convenir bajar un poco el precio o activar una promoción en Airbnb. Mirá la sección Precios.",
                f"calendario?propiedad_id={p['id']}")

    # 10) Precio base muy lejos del mercado
    try:
        import competencia_auto, competencia_ia
        for p in props:
            if not p.get("precio_base") or not (p.get("barrio") or "").strip():
                continue
            st = competencia_ia.calcular_stats(competencia_auto.comparables_vigentes(p["id"], p.get("barrio")),
                                               p.get("moneda") or "ARS", monedas.tc_valor())
            if st and st["cantidad"] >= 5 and st["mediana"]:
                dif = (p["precio_base"] - st["mediana"]) / st["mediana"] * 100
                if abs(dif) >= 30:
                    add("info", f"{p['nombre']}: tu precio está {abs(dif):.0f}% {'por debajo' if dif < 0 else 'por encima'} del mercado",
                        f"Tu precio base es {monedas.formatear(p['precio_base'], p.get('moneda') or 'ARS')} y la mediana de la zona "
                        f"{monedas.formatear(st['mediana'], p.get('moneda') or 'ARS')}. "
                        + ("Podrías estar dejando plata sobre la mesa." if dif < 0 else "Puede costarte reservas."),
                        f"precios?propiedad_id={p['id']}&resaltar=mercado")
    except Exception as e:
        print(f"[alertas] mercado: {e}")

    # 11) El mes viene en rojo (desde el día 20)
    if hoy.day >= 20 and reservas:
        d1 = hoy.replace(day=1)
        conv, _ = monedas.convertir_reservas(metricas.filtrar_reservas(reservas, d1, hoy), "ARS", monedas.tc_valor())
        costos = monedas.costos_mensuales([p for p in props if (p.get("estado") or "activa") != "inactiva"], "ARS", monedas.tc_valor())
        m = metricas.calcular_metricas(conv, d1, hoy, costos, max(len(props), 1))
        if m and m["ingreso_neto_real"] < 0:
            add("alta", "Este mes los costos superan a los ingresos",
                f"Ingreso neto real del mes: {monedas.formatear(m['ingreso_neto_real'], 'ARS')}. Revisá precios y ocupación.", "?resaltar=neto")

    al.sort(key=lambda a: ORDEN[a["nivel"]])
    for a in al:   # ### CAMBIO AQUÍ ### identificador estable (no cambia con los montos del día)
        a["clave"] = hashlib.sha1(f"{a['titulo']}|{a['link']}".encode()).hexdigest()[:12]
    return al


# ════════════ ### CAMBIO AQUÍ ### OCULTAR ALERTAS ════════════
# Se guardan en config como {clave: "fecha hasta la que no se muestra"}. Las alertas no se borran:
# si el problema sigue, vuelve a aparecer pasado el plazo.
def _leer_ocultas():
    fila = db.query_one("SELECT valor FROM config WHERE clave = 'alertas_ocultas'")
    try:
        datos = json.loads(fila["valor"]) if fila and fila["valor"] else {}
        return datos if isinstance(datos, dict) else {}
    except (ValueError, TypeError):
        return {}


def _guardar_ocultas(datos):
    db.execute("""INSERT INTO config (clave, valor) VALUES ('alertas_ocultas', %s)
                  ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor""", (json.dumps(datos),))


def ocultar(clave, hoy=None):
    if not clave or len(clave) > 40:
        return
    hoy = hoy or date.today()
    datos = {k: v for k, v in _leer_ocultas().items() if v >= hoy.isoformat()}   # limpia las vencidas
    datos[clave] = (hoy + timedelta(days=DIAS_OCULTA)).isoformat()
    _guardar_ocultas(datos)


def mostrar_todas():
    _guardar_ocultas({})


def separar(lista, hoy=None):
    """Devuelve (visibles, ocultas)."""
    hoy = (hoy or date.today()).isoformat()
    datos = _leer_ocultas()
    vis, ocu = [], []
    for a in lista:
        hasta = datos.get(a.get("clave"))
        if hasta and hasta >= hoy:
            a["oculta_hasta"] = hasta
            ocu.append(a)
        else:
            vis.append(a)
    return vis, ocu
