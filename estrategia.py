# estrategia.py
# ### CAMBIO AQUÍ ### — Archivo nuevo: "Qué hacer hoy" y la página Estrategia.
#
# Regla de oro: cada número que se muestra lleva su explicación (de dónde sale, cómo se calculó y con qué
# reservas). Si no hay datos suficientes, se dice "no hay datos" en vez de inventar.
#
# Fuentes que usa:
#   - Reservas cargadas desde los archivos de Airbnb (precio, noches, cuándo se reservó).
#   - Calendario iCal de Airbnb (qué noches están ocupadas hoy), si Adriano pegó el link.
#   - Costos por recambio que carga Adriano en cada propiedad.
#   - Feriados (fuente oficial) y eventos que carga Adriano.

import statistics
from datetime import date, timedelta

import database as db
import disposicion_pago as dp
import feriados as fer
import ical
import metricas
import monedas

DIAS_ADELANTE = 90
MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
TRAMOS = [(1, 3, "1 a 3 noches"), (4, 6, "4 a 6 noches"), (7, 13, "1 a 2 semanas"),
          (14, 27, "2 a 4 semanas"), (28, 10_000, "28 noches o más")]


def _f(d):
    return f"{DIAS[d.weekday()]} {d.day}/{d.month}"


def _rango_txt(a, b):
    """a y b incluidos."""
    return _f(a) if a == b else f"{_f(a)} al {_f(b)}"


def _redondeo(v, mon):
    paso = 500 if mon == "ARS" and v >= 5000 else (1 if mon == "USD" else 100)
    return int(round(v / paso) * paso) if paso > 1 else round(v)


# ═══════════════ COSTOS DE RECAMBIO ═══════════════
def recambio(prop):
    partes = {"limpieza": prop.get("recambio_limpieza") or 0, "lavandería": prop.get("recambio_lavanderia") or 0,
              "toallas e insumos": prop.get("recambio_insumos") or 0}
    total = round(sum(partes.values()), 2)
    return {"partes": partes, "total": total, "cargado": total > 0}


# ═══════════════ HISTORIA DE LA PROPIEDAD ═══════════════
def historia(prop, reservas, hoy, tc):
    mon = prop.get("moneda") or "ARS"
    propias = [r for r in reservas if r.get("propiedad_id") == prop["id"]]
    conv, sin_tc = monedas.convertir_reservas(propias, mon, tc)
    validas = dp._validas(conv)
    ultimo_anio = [v for v in validas if hoy - timedelta(days=365) <= v["fi"] <= hoy + timedelta(days=DIAS_ADELANTE)]
    con_precio = [v for v in ultimo_anio if v["precio"]]
    precios = [v["precio"] for v in con_precio]
    limpiezas = [(v["r"].get("limpieza") or 0) for v in con_precio]
    leads = [v["ant"] for v in validas if v["ant"] is not None]
    h = {"mon": mon, "validas": validas, "con_precio": con_precio, "sin_tc": sin_tc,
         "mediana": round(statistics.median(precios)) if len(precios) >= 3 else None,
         "n": len(precios),
         "desde": min((v["fi"] for v in con_precio), default=None),
         "hasta": max((v["fi"] for v in con_precio), default=None),
         "limpieza_cobrada": round(statistics.mean([x for x in limpiezas if x > 0])) if any(x > 0 for x in limpiezas) else 0,
         "leads": sorted(leads)}
    if h["mediana"]:
        h["base"], h["base_txt"] = h["mediana"], (
            f"lo que te pagaron por noche en tus últimas {h['n']} reservas (del {h['desde'].strftime('%d/%m/%Y')} "
            f"al {h['hasta'].strftime('%d/%m/%Y')}), sin limpieza: la mitad pagó más y la mitad menos")
    elif prop.get("precio_base"):
        h["base"], h["base_txt"] = prop["precio_base"], ("tu precio base cargado en la propiedad (todavía hay menos de 3 "
                                                          "reservas con precio para usar tu historial)")
    else:
        h["base"], h["base_txt"] = None, ""
    return h


# ═══════════════ ESTADÍA MÍNIMA ═══════════════
def estadia_minima(prop, h):
    mon, rc = h["mon"], recambio(prop)
    filas, sin_datos = [], []
    for a, b, nombre in TRAMOS:
        grupo = [v for v in h["con_precio"] if a <= v["n"] <= b]
        if len(grupo) < 2:
            sin_datos.append(nombre)
            continue
        noches = sum(v["n"] for v in grupo)
        precio = round(sum(v["precio"] * v["n"] for v in grupo) / noches)
        L = round(noches / len(grupo), 1)   # el mismo número que se muestra, así la cuenta se puede verificar a mano
        limp = statistics.mean([(v["r"].get("limpieza") or 0) for v in grupo])
        neto = round(precio + limp / L - rc["total"] / L) if rc["cargado"] else None
        Lt = f"{L:.1f}".replace(".", ",")
        explica = [f"{len(grupo)} reservas de {nombre} en el último año; se quedaron {Lt} noches en promedio.",
                   f"Te pagaron {monedas.formatear(precio, mon)} por noche en promedio (sin limpieza)."]
        if limp > 0:
            explica.append(f"Además cobraste {monedas.formatear(limp, mon)} de limpieza por estadía → "
                           f"+{monedas.formatear(limp / L, mon)} por noche.")
        if rc["cargado"]:
            explica.append(f"Cada salida te cuesta {monedas.formatear(rc['total'], mon)} → "
                           f"−{monedas.formatear(rc['total'] / L, mon)} por noche (repartido en {Lt} noches).")
            explica.append(f"Te queda: {monedas.formatear(neto, mon)} por noche vendida.")
        filas.append({"nombre": nombre, "reservas": len(grupo), "noches_prom": round(L, 1), "precio": precio,
                      "limpieza": round(limp), "recambio_noche": round(rc["total"] / L) if rc["cargado"] else None,
                      "neto": neto, "explica": explica, "min": a})
    conclusion = None
    con_neto = [f for f in filas if f["neto"] is not None and f["reservas"] >= 3]   # con menos de 3 no se concluye nada
    if len(con_neto) >= 2:
        corto, largo = con_neto[0], con_neto[-1]
        if largo["neto"] > 0 and corto["neto"] < largo["neto"]:
            pct = round((1 - corto["neto"] / largo["neto"]) * 100)
            conclusion = (f"Por cada noche vendida, las estadías de {largo['nombre']} te dejan "
                          f"{monedas.formatear(largo['neto'] - corto['neto'], mon)} más que las de {corto['nombre']}. "
                          f"Siguen conviniendo aunque vendas hasta un {pct}% menos de noches.")
            conclusion_min = largo["min"]
        elif corto["neto"] > 0 and corto["neto"] >= largo["neto"]:
            pct = round((corto["neto"] / largo["neto"] - 1) * 100) if largo["neto"] > 0 else None
            conclusion = (f"Por cada noche vendida, las estadías de {corto['nombre']} te dejan "
                          f"{monedas.formatear(corto['neto'] - largo['neto'], mon)} más que las de {largo['nombre']}. "
                          + (f"Las largas solo convienen si con ellas vendés al menos un {pct}% más de noches."
                             if pct is not None else "Las largas hoy no te dejan ganancia por noche."))
            conclusion_min = corto["min"]
        else:
            conclusion_min = None
        if conclusion:
            conclusion += (" Ojo: esto compara cuánto te queda por noche vendida; no sabe cuántas noches vas a vender "
                           "con cada mínimo. Eso lo muestra tu ocupación cuando lo pruebes.")
    else:
        conclusion_min = None
    return {"filas": filas, "sin_datos": sin_datos, "conclusion": conclusion, "sugerido": conclusion_min,
            "recambio": rc, "con_neto": len(con_neto)}


# ═══════════════ NOCHES OCUPADAS Y HUECOS ═══════════════
def ocupadas(prop, h, hoy, dias=DIAS_ADELANTE):
    fin = hoy + timedelta(days=dias)
    out = set()
    for v in h["validas"]:
        d = max(v["fi"], hoy)
        while d < min(v["ff"], fin):
            out.add(d)
            d += timedelta(days=1)
    fuente = "tus reservas cargadas"
    if (prop.get("ical_url") or "").strip():
        cuando, error = ical.ultimo(prop["id"])
        if cuando:
            out |= ical.noches_ocupadas(prop["id"], hoy, fin)
            fuente += " + el calendario de Airbnb"
    return out, fuente


def tramos_libres(ocup, hoy, dias=DIAS_ADELANTE):
    """[(desde, hasta_incluida, cerrado_a_la_derecha)]"""
    out, d, fin = [], hoy, hoy + timedelta(days=dias)
    while d < fin:
        if d in ocup:
            d += timedelta(days=1)
            continue
        ini = d
        while d < fin and d not in ocup:
            d += timedelta(days=1)
        out.append((ini, d - timedelta(days=1), d < fin))
    return out


# ═══════════════ PRECIO POR NOCHE ═══════════════
def _contexto_precio(prop, h, hoy, especiales, ritmo):
    mon = h["mon"]
    costos_fijos = sum((prop.get(k) or 0) for k in ("costo_expensas", "costo_servicios", "costo_limpieza", "costo_comision"))
    rc = recambio(prop)
    L = statistics.median([v["n"] for v in h["con_precio"]]) if h["con_precio"] else (prop.get("estadia_minima") or 3)
    piso = costos_fijos / 30.44 + (rc["total"] / L if rc["cargado"] else 0)
    piso_txt = (f"no baja de {monedas.formatear(_redondeo(piso, mon), mon)}: tus costos fijos por noche "
                f"({monedas.formatear(costos_fijos / 30.44, mon)})"
                + (f" + el recambio repartido en tu estadía típica de {L:g} noches ({monedas.formatear(rc['total'] / L, mon)})"
                   if rc["cargado"] else ""))
    # efecto del mes: solo si hay datos de ese mes
    por_mes = {}
    for v in h["con_precio"]:
        por_mes.setdefault(v["fi"].month, []).append(v["precio"])
    return {"mon": mon, "piso": piso, "piso_txt": piso_txt, "por_mes": por_mes, "especiales": especiales,
            "ritmo": ritmo, "hoy": hoy, "base": h["base"], "base_txt": h["base_txt"], "leads": h["leads"], "mediana": h["mediana"]}


def precio_noche(d, cx):
    """(precio, [motivos]) o (None, [motivo]) si no hay base."""
    mon = cx["mon"]
    if not cx["base"]:
        return None, ["Falta un precio de partida: cargá el precio base de la propiedad o subí el archivo de Reservas."]
    p = cx["base"]
    motivos = [f"Punto de partida {monedas.formatear(p, mon)}: {cx['base_txt']}."]
    mes = cx["por_mes"].get(d.month, [])
    if cx["mediana"] and len(mes) >= 3 and sum(len(x) for x in cx["por_mes"].values()) >= 8:
        f = max(0.7, min(1.4, statistics.median(mes) / cx["mediana"]))
        if abs(f - 1) >= 0.03:
            p *= f
            motivos.append(f"En {MESES[d.month]} te pagaron {abs(round((f - 1) * 100))}% {'más' if f > 1 else 'menos'} "
                           f"que en el resto del año ({len(mes)} reservas de {MESES[d.month]}).")
    k = (d - cx["hoy"]).days
    r = cx["ritmo"].get(k)
    vende_rapido = bool(r and r["tipo"] == "subir")
    if r:
        if r["tipo"] == "subir" and r["vendidas"] < r["noches"]:
            f = 1.10 if r["real"] >= r["esperado"] * 1.3 else 1.05
            p *= f
            motivos.append(f"+{round((f - 1) * 100)}%: para esas fechas ({r['nombre'].lower()}) ya vendiste {r['real']}% de las "
                           f"noches y normalmente a esta altura tenés {r['esperado']}%.")
        elif r["tipo"] == "bajar":
            p *= 0.95
            motivos.append(f"−5%: para esas fechas ({r['nombre'].lower()}) vendiste {r['real']}% y lo normal a esta altura es "
                           f"{r['esperado']}%.")
    leads = cx["leads"]
    if k <= 7 and len(leads) >= 5 and not vende_rapido:   # si se vende rápido, no se regala la última noche
        ultimo_momento = sum(1 for x in leads if x <= k) / len(leads)
        if ultimo_momento <= 0.30:
            f = 0.90 if k <= 3 else 0.95
            p *= f
            motivos.append(f"−{round((1 - f) * 100)}%: faltan {k} días y sigue libre. Solo el {round(ultimo_momento * 100)}% "
                           f"de tus reservas se hizo con {k} días o menos de anticipación.")
    esp = cx["especiales"].get(d)
    if esp and esp[1]:
        p *= 1 + esp[1] / 100
        motivos.append(f"+{esp[1]}%: {esp[0]}.")
    if p < cx["piso"]:
        p = cx["piso"]
        motivos.append(f"Se subió al mínimo: {cx['piso_txt']}.")
    return _redondeo(p, mon), motivos


def ritmo_por_dia(analisis):
    """{días desde hoy: fila de ritmo} a partir del análisis de disposicion_pago."""
    out = {}
    if analisis and analisis.get("ritmo"):
        for (a, b, _), fila in zip(dp.VENTANAS, analisis["ritmo"]["filas"]):
            for k in range(a, b + 1):
                out[k] = fila
    return out


def precios_libres(prop, h, ocup, cx, hoy, dias=30):
    """Noches libres de los próximos días con su precio sugerido, agrupadas cuando se repiten."""
    grupos = []
    for k in range(dias):
        d = hoy + timedelta(days=k)
        if d in ocup:
            continue
        p, mot = precio_noche(d, cx)
        if grupos and grupos[-1]["precio"] == p and grupos[-1]["motivos"][1:] == mot[1:] \
                and grupos[-1]["hasta"] == d - timedelta(days=1):
            grupos[-1]["hasta"] = d
        else:
            grupos.append({"desde": d, "hasta": d, "precio": p, "motivos": mot})
    for g in grupos:
        g["txt"] = _rango_txt(g["desde"], g["hasta"])
    return grupos


# ═══════════════ DESCUENTOS ═══════════════
def descuentos(prop, h, cx, em):
    mon, rc = h["mon"], recambio(prop)
    out = {"vacia": None, "mensual": None}
    base = cx["base"]
    if base:
        maximo = max(0, 1 - cx["piso"] / base)
        out["vacia"] = {"pct": round(maximo * 100), "explica": [
            f"Tu precio de partida es {monedas.formatear(base, mon)} ({cx['base_txt']}).",
            f"Una noche vendida tiene que cubrir al menos {monedas.formatear(cx['piso'], mon)} ({cx['piso_txt'].split(': ', 1)[-1]}).",
            f"Entonces podés descontar hasta {round(maximo * 100)}% antes de perder plata. Una noche vacía no deja nada, "
            f"así que cualquier descuento por debajo de eso es mejor que dejarla libre."]}
    cortas = [v for v in h["con_precio"] if v["n"] < 28]
    if base and rc["cargado"] and len(cortas) >= 3:
        Ls = statistics.median([v["n"] for v in cortas])
        C = h["limpieza_cobrada"]
        neto_corto = base + (C - rc["total"]) / Ls
        d = 1 - (neto_corto - (C - rc["total"]) / 28) / base
        out["mensual"] = {"pct": max(0, round(d * 100)), "Ls": Ls, "explica": [
            f"Tus estadías cortas duran {Ls:g} noches (mediana de {len(cortas)} reservas de menos de 28 noches).",
            f"Con estadías así, por noche te queda {monedas.formatear(neto_corto, mon)}: "
            f"{monedas.formatear(base, mon)} de precio" + (f" + {monedas.formatear(C / Ls, mon)} de limpieza cobrada" if C else "")
            + f" − {monedas.formatear(rc['total'] / Ls, mon)} de recambio.",
            f"En una estadía de 28 noches el recambio se reparte en 28 noches y casi desaparece "
            f"({monedas.formatear(rc['total'] / 28, mon)} por noche).",
            (f"Por eso podés dar hasta {max(0, round(d * 100))}% de descuento mensual y te queda lo mismo por noche que con "
             f"estadías cortas (suponiendo que las noches se venden igual)." if d > 0 else
             "Con tus números, un descuento mensual te deja menos por noche que las estadías cortas.")]}
    return out


def pruebas(prop, h, hoy):
    """Qué pasó después de cada prueba de descuento: reservas hechas 14 días antes vs 14 días después."""
    out = []
    for p in db.query("SELECT * FROM pruebas_descuento WHERE propiedad_id=%s ORDER BY fecha DESC, id DESC LIMIT 20", (prop["id"],)):
        f = metricas._parse(p["fecha"])
        if not f:
            continue

        def resumen(a, b):
            g = [v for v in h["validas"] if v["fr"] and a <= v["fr"] < b]
            precios = [v["precio"] for v in g if v["precio"]]
            return {"reservas": len(g), "noches": sum(v["n"] for v in g),
                    "precio": round(statistics.mean(precios)) if precios else None}
        antes = resumen(f - timedelta(days=14), f)
        despues = resumen(f, min(f + timedelta(days=14), hoy + timedelta(days=1)))
        faltan = max(0, (f + timedelta(days=14) - hoy).days)
        out.append({**p, "antes": antes, "despues": despues, "faltan": faltan})
    return out


# ═══════════════ ARMADO COMPLETO DE UNA PROPIEDAD ═══════════════
def analizar(prop, reservas, hoy=None, tc=None, lista_esp=None):
    hoy = hoy or date.today()
    h = historia(prop, reservas, hoy, tc)
    if lista_esp is None:
        lista_esp, _ = fer.proximos(hoy, DIAS_ADELANTE)
    especiales = fer.noches_especiales(lista_esp)
    try:
        a_dp = dp.analizar(prop, reservas, hoy, None, tc)
    except Exception:
        a_dp = None
    cx = _contexto_precio(prop, h, hoy, especiales, ritmo_por_dia(a_dp))
    ocup, fuente = ocupadas(prop, h, hoy)
    em = estadia_minima(prop, h)
    return {"prop": prop, "h": h, "cx": cx, "ocup": ocup, "fuente": fuente, "em": em, "dp": a_dp,
            "precios": precios_libres(prop, h, ocup, cx, hoy), "desc": descuentos(prop, h, cx, em),
            "pruebas": pruebas(prop, h, hoy), "libres": tramos_libres(ocup, hoy), "esp": lista_esp, "hoy": hoy}


# ═══════════════ ACCIONES DE "QUÉ HACER HOY" ═══════════════
def acciones(a):
    prop, h, cx, hoy = a["prop"], a["h"], a["cx"], a["hoy"]
    pid, mon = prop["id"], h["mon"]
    minima = prop.get("estadia_minima")
    rc = a["em"]["recambio"]
    out = []

    def add(clave, cuando, titulo, hacer, origen, link=None):
        out.append({"clave": f"{pid}:{clave}", "cuando": cuando, "titulo": titulo, "hacer": hacer,
                    "origen": origen, "link": link, "prop_id": pid, "prop": prop["nombre"]})

    # 1) datos que faltan (sin ellos los cálculos quedan cortos)
    if not h["validas"]:
        add("cfg:sin_reservas", "hoy", "Subí el archivo de Reservas de Airbnb",
            "Importar CSV → elegí el archivo de Reservas que exportás de Airbnb.",
            ["Sin reservas cargadas no hay historial para calcular precios ni ritmo de ventas."], "importar?resaltar=subir-reservas")
    if not rc["cargado"]:
        add("cfg:recambio", "semana", "Completá cuánto te cuesta cada recambio",
            "Propiedades → Editar → sección 'Costos por cada salida de huésped'.",
            ["Con ese dato el sistema compara estadías cortas contra largas y calcula hasta cuánto descuento conviene."],
            f"propiedades/{pid}/editar?resaltar=recambio_limpieza")
    if not minima:
        add("cfg:minima", "semana", "Anotá la estadía mínima que tenés en Airbnb",
            "Propiedades → Editar → 'Estadía mínima actual en Airbnb'.",
            ["Sirve para detectar noches que quedan libres entre dos reservas y nadie puede reservar."],
            f"propiedades/{pid}/editar?resaltar=estadia_minima")
    url = (prop.get("ical_url") or "").strip()
    cuando_ical, error_ical = ical.ultimo(pid) if url else (None, "")
    if not url:
        add("cfg:ical", "semana", "Conectá el calendario de Airbnb",
            "En Airbnb: Calendario → Disponibilidad → Conectar calendarios → Exportar calendario → copiá el link "
            "y pegalo en Propiedades → Editar → 'Link del calendario de Airbnb'.",
            ["Con el calendario conectado, el sistema sabe cada hora qué noches siguen libres sin esperar a que subas archivos."],
            f"propiedades/{pid}/editar?resaltar=ical_url")
    elif error_ical:
        add(f"cfg:ical_error:{hoy}", "hoy", "No se pudo leer el calendario de Airbnb",
            "Revisá que el link del calendario siga siendo el de Airbnb (Exportar calendario) y volvé a pegarlo.",
            [f"Último error: {error_ical}"], f"propiedades/{pid}/editar?resaltar=ical_url")
    if not url:
        f_imp = metricas._parse((db.query_one("SELECT valor FROM config WHERE clave='ultima_importacion_reservas'") or {}).get("valor"))
        if h["validas"] and (not f_imp or (hoy - f_imp).days > 7):
            add(f"cfg:archivo:{hoy.isocalendar()[1]}", "hoy", "Subí el archivo de Reservas actualizado",
                "Exportá las reservas de Airbnb y subilas en Importar CSV, renglón Reservas.",
                [("El último archivo de Reservas es del " + f_imp.strftime("%d/%m") if f_imp else "Nunca se subió el archivo de Reservas")
                 + ". Sin calendario conectado, las sugerencias de hoy pueden estar viejas."], "importar?resaltar=subir-reservas")

    # 2) noches libres de los próximos 7 días → precio de último momento
    huecos_hechos = set()
    for ini, fin, cerrado in a["libres"]:
        if ini > hoy + timedelta(days=6):
            break
        fin7 = min(fin, hoy + timedelta(days=6))
        largo_total = (fin - ini).days + 1
        p, mot = precio_noche(ini, cx)
        if p is None:
            continue
        extra = ""
        if minima and cerrado and largo_total < minima:
            huecos_hechos.add(ini)
            neto = p + (h["limpieza_cobrada"] - rc["total"]) / largo_total if rc["cargado"] else None
            if neto is not None and neto <= 0:
                add(f"hueco_no:{ini}:{fin}", "hoy", f"{_rango_txt(ini, fin)}: no vale la pena abrirlo", "Dejá esas noches como están.",
                    [f"Son {largo_total} noche(s) libres entre dos reservas y tu estadía mínima es {minima}.",
                     f"Una estadía de {largo_total} noche(s) a {monedas.formatear(p, mon)} te deja {monedas.formatear(neto, mon)} "
                     f"por noche después del recambio ({monedas.formatear(rc['total'], mon)})."])
                continue
            extra = f" y bajá la estadía mínima a {largo_total} noche{'s' if largo_total > 1 else ''} para esas fechas"
            mot = mot + [f"Son {largo_total} noches libres entre dos reservas y tu estadía mínima es {minima}: "
                         f"si no la bajás, nadie las puede reservar."] + (
                [f"Aun pagando el recambio ({monedas.formatear(rc['total'], mon)}) te quedan "
                 f"{monedas.formatear(neto, mon)} por noche."] if neto is not None else [])
        add(f"libre:{ini}:{fin7}:{p}", "hoy", f"Libre {_rango_txt(ini, fin7)}: poné {monedas.formatear(p, mon)} por noche",
            f"Airbnb → Calendario → seleccioná {_rango_txt(ini, fin7)} → precio por noche {monedas.formatear(p, mon)}{extra}.",
            mot + [f"Noches ocupadas según {a['fuente']}."], f"estrategia?propiedad_id={pid}&resaltar=precios")

    # 3) huecos más cortos que la estadía mínima (más adelante)
    if minima:
        for ini, fin, cerrado in a["libres"]:
            largo = (fin - ini).days + 1
            if ini in huecos_hechos or not cerrado or largo >= minima or ini <= hoy + timedelta(days=6):
                continue
            if ini > hoy + timedelta(days=60):
                break
            p, _ = precio_noche(ini, cx)
            cuando = "semana" if ini <= hoy + timedelta(days=14) else "mes"
            neto = (p or 0) + (h["limpieza_cobrada"] - rc["total"]) / largo if rc["cargado"] else None
            if neto is not None and neto <= 0:
                add(f"hueco_no:{ini}:{fin}", cuando, f"{_rango_txt(ini, fin)}: no vale la pena abrirlo",
                    "Dejá esas noches como están.",
                    [f"Son {largo} noche(s) libres entre dos reservas.",
                     f"Una estadía de {largo} noche(s) a {monedas.formatear(p, mon)} te deja "
                     f"{monedas.formatear(neto, mon)} por noche después del recambio ({monedas.formatear(rc['total'], mon)})."])
                continue
            add(f"hueco:{ini}:{fin}", cuando, f"{_rango_txt(ini, fin)}: {largo} noche{'s' if largo > 1 else ''} que nadie puede reservar",
                f"Airbnb → Calendario → seleccioná {_rango_txt(ini, fin)} → Estadía mínima: {largo} noche{'s' if largo > 1 else ''}.",
                [f"Quedan {largo} noches libres entre dos reservas y tu estadía mínima es {minima}.",
                 f"Noches ocupadas según {a['fuente']}."]
                + ([f"Aun con el recambio ({monedas.formatear(rc['total'], mon)}) te quedan "
                    f"{monedas.formatear(neto, mon)} por noche."] if neto is not None else []))

    # 4) ritmo de ventas más adelante
    if a["dp"] and a["dp"].get("ritmo"):
        semana = hoy.isocalendar()[1]
        for (a0, b0, _), fila in list(zip(dp.VENTANAS, a["dp"]["ritmo"]["filas"]))[1:]:
            d1, d2 = hoy + timedelta(days=a0), hoy + timedelta(days=b0)
            cuando = "semana" if a0 < 30 else "mes"
            base_txt = (f"Para {_rango_txt(d1, d2)} ya vendiste {fila['vendidas']} de {fila['noches']} noches ({fila['real']}%). "
                        f"Normalmente, a esta misma distancia, tenés {fila['esperado']}% vendido "
                        f"(calculado con tus últimos {a['dp']['ritmo']['dias_hist']} días de reservas).")
            if fila["tipo"] == "subir" and fila["vendidas"] < fila["noches"]:
                pct = 10 if fila["real"] >= fila["esperado"] * 1.3 else 5
                add(f"ritmo:{a0}:subir:{semana}", cuando, f"{_rango_txt(d1, d2)}: subí {pct}% las noches libres",
                    f"Airbnb → Calendario → seleccioná las noches libres de {_rango_txt(d1, d2)} → subí el precio {pct}%.",
                    [base_txt, "Se está vendiendo más rápido que lo normal: a ese precio sobra demanda."],
                    f"precios?propiedad_id={pid}&resaltar=ritmo")
            elif fila["tipo"] == "bajar":
                add(f"ritmo:{a0}:bajar:{semana}", cuando, f"{_rango_txt(d1, d2)}: viene más flojo que lo normal",
                    "No subas el precio. Si en una semana sigue igual, bajá 5% o activá una promoción de Airbnb para esas fechas.",
                    [base_txt], f"precios?propiedad_id={pid}&resaltar=ritmo")

    # 5) feriados y eventos con noches libres
    libres_set = {hoy + timedelta(days=k) for k in range(DIAS_ADELANTE)} - a["ocup"]
    vistos = set()
    for x in a["esp"]:
        noches = [n for n, (nombre, _) in fer.noches_especiales([x]).items()]
        libres_x = sorted(n for n in noches if n in libres_set and n > hoy + timedelta(days=6))
        # solo los próximos 45 días (los más lejanos se ven en Estrategia, para no llenar la pantalla)
        if not libres_x or libres_x[0] > hoy + timedelta(days=45) or (x["nombre"], x["desde"]) in vistos or not x["impacto"]:
            continue
        vistos.add((x["nombre"], x["desde"]))
        cuando = "semana" if libres_x[0] <= hoy + timedelta(days=14) else "mes"
        p, _ = precio_noche(libres_x[0], cx)
        add(f"esp:{x['nombre']}:{x['desde']}", cuando,
            f"{x['nombre']} ({_rango_txt(x['desde'], x['hasta'])}): subí {x['impacto']}%",
            f"Airbnb → Calendario → seleccioná {_rango_txt(libres_x[0], libres_x[-1])} → subí el precio {x['impacto']}%"
            + (f" (≈ {monedas.formatear(p, mon)} por noche)." if p else "."),
            [("Feriado nacional" + (" (fuente oficial)." if x["origen"] == "oficial" else " (calculado: no hubo conexión con la fuente oficial).")
              if x["tipo"] == "feriado" else f"Evento cargado por vos, con impacto de +{x['impacto']}%."),
             "Cuando hay feriado, la gente viaja la noche anterior y la del feriado (o todo el fin de semana largo).",
             f"{len(libres_x)} de esas noches siguen libres."])

    # 6) estadía mínima: probar otra si los números lo justifican
    em = a["em"]
    if em["sugerido"] and minima and em["sugerido"] != minima and em["con_neto"] >= 2 \
            and all(f["reservas"] >= 3 for f in em["filas"] if f["neto"] is not None):
        add(f"minima:{em['sugerido']}:{hoy.strftime('%Y-%m')}", "mes", f"Probá estadía mínima de {em['sugerido']} noches",
            f"Airbnb → Calendario → Configuración → Duración del viaje → estadía mínima {em['sugerido']} noches. "
            f"Volvé a mirar la ocupación en 3 o 4 semanas.",
            [em["conclusion"]], f"estrategia?propiedad_id={pid}&resaltar=estadia")

    hechas = {f["clave"] for f in db.query("SELECT clave FROM acciones_estado WHERE clave = ANY(%s)",
                                           ([x["clave"] for x in out],))} if out else set()
    return [x for x in out if x["clave"] not in hechas]


# ═══════════════ COMENTARIOS DE ADRIANO ═══════════════
def comentarios(claves):
    if not claves:
        return {}
    out = {}
    for c in db.query("SELECT * FROM comentarios WHERE clave = ANY(%s) ORDER BY creado_en, id", (list(claves),)):
        out.setdefault(c["clave"], []).append(c)
    return out


def comentarios_recientes(limite=30):
    return db.query("SELECT * FROM comentarios ORDER BY creado_en DESC, id DESC LIMIT %s", (limite,))


# ═══════════════ RESUMEN PARA EL ASISTENTE IA ═══════════════
def resumen_ia(hoy=None, tc=None):
    """Texto compacto con la estrategia de cada propiedad activa (sin nombres de huéspedes)."""
    hoy = hoy or date.today()
    props = db.query("SELECT * FROM propiedades WHERE COALESCE(estado,'activa') = 'activa' ORDER BY nombre")
    if not props:
        return "Sin propiedades activas."
    reservas = db.query("SELECT * FROM reservas")
    try:
        lista_esp, _ = fer.proximos(hoy, DIAS_ADELANTE)
    except Exception:
        lista_esp = []
    bloques = []
    for p in props:
        try:
            a = analizar(p, reservas, hoy, tc, lista_esp)
            acc = acciones(a)
        except Exception as e:
            bloques.append(f"### {p['nombre']}: no se pudo calcular ({e})")
            continue
        mon, em, cx = a["h"]["mon"], a["em"], a["cx"]
        L = [f"### {p['nombre']} (moneda {mon})",
             f"- Precio de partida: {monedas.formatear(cx['base'], mon) + ' — ' + cx['base_txt'] if cx['base'] else 'sin datos'}",
             f"- Costo por recambio: {monedas.formatear(em['recambio']['total'], mon) if em['recambio']['cargado'] else 'NO CARGADO'}"
             f" | Estadía mínima en Airbnb: {p.get('estadia_minima') or 'no cargada'}"
             f" | Piso por noche: {monedas.formatear(cx['piso'], mon)} ({cx['piso_txt']})",
             f"- Noches ocupadas próximos {DIAS_ADELANTE} días: {len(a['ocup'])} (según {a['fuente']})"]
        if em["filas"]:
            L.append("- Comparación por duración de estadía (último año): " + "; ".join(
                f"{f['nombre']}: {f['reservas']} reservas, {monedas.formatear(f['precio'], mon)}/noche"
                + (f", te queda {monedas.formatear(f['neto'], mon)}/noche" if f["neto"] is not None else "") for f in em["filas"]))
            if em["conclusion"]:
                L.append(f"- Conclusión estadías: {em['conclusion']}")
        if a["desc"]["vacia"]:
            L.append(f"- Descuento máximo para no dejar una noche vacía: {a['desc']['vacia']['pct']}%")
        if a["desc"]["mensual"]:
            L.append(f"- Descuento mensual equivalente a estadías cortas: {a['desc']['mensual']['pct']}%")
        if a["dp"] and a["dp"].get("ritmo"):
            L.append("- Ritmo de ventas: " + "; ".join(f"{f['nombre']}: {f['real']}% vendido vs {f['esperado']}% normal"
                                                       for f in a["dp"]["ritmo"]["filas"]))
        if a["precios"]:
            L.append("- Precio sugerido noches libres (próx. 30 días): " + "; ".join(
                f"{g['txt']}: {monedas.formatear(g['precio'], mon) if g['precio'] else 'sin base'}" for g in a["precios"][:10]))
        for pr in a["pruebas"][:5]:
            L.append(f"- Prueba {pr['fecha']} {pr['tipo']} {pr['porcentaje'] or ''}%: 14 días antes {pr['antes']['reservas']} reservas, "
                     f"después {pr['despues']['reservas']}" + (f" (faltan {pr['faltan']} días)" if pr["faltan"] else ""))
        if acc:
            L.append("- Acciones pendientes: " + " | ".join(f"[{x['cuando']}] {x['titulo']} → {x['hacer']}" for x in acc))
        bloques.append("\n".join(L))
    if lista_esp:
        bloques.append("### Feriados y eventos próximos\n" + "\n".join(
            f"- {x['desde'].strftime('%d/%m')}" + (f" al {x['hasta'].strftime('%d/%m')}" if x["hasta"] != x["desde"] else "")
            + f": {x['nombre']} ({x['tipo']}, {x['impacto']:+d}%)" for x in lista_esp[:15]))
    com = comentarios_recientes(20)
    if com:
        bloques.append("### Comentarios y correcciones de Adriano (tenelos en cuenta: corrigen al sistema)\n" + "\n".join(
            f"- {c['creado_en'].strftime('%d/%m') if c['creado_en'] else ''} [{c['clave']}]: {c['texto'][:200]}" for c in com))
    return "\n\n".join(bloques)
