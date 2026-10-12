# feriados.py
# ### CAMBIO AQUÍ ### — Archivo nuevo: feriados de Argentina (y eventos que carga Adriano).
#
# Fuente: api.argentinadatos.com (datos públicos del calendario oficial). Se guarda una copia por año
# y se renueva cada 30 días. Si no hay conexión, se usa un cálculo de respaldo con los feriados fijos
# y los de Semana Santa/Carnaval (los "puentes" turísticos no se pueden calcular: solo vienen de la fuente).

import json
import urllib.request
from datetime import date, datetime, timedelta, timezone

import database as db

URL = "https://api.argentinadatos.com/v1/feriados/{anio}"
RENOVAR_DIAS = 30

FIJOS = [(1, 1, "Año Nuevo"), (3, 24, "Día de la Memoria"), (4, 2, "Día del Veterano y de los Caídos en Malvinas"),
         (5, 1, "Día del Trabajador"), (5, 25, "Revolución de Mayo"), (6, 20, "Día de la Bandera"),
         (7, 9, "Día de la Independencia"), (12, 8, "Inmaculada Concepción"), (12, 25, "Navidad")]
# trasladables: martes/miércoles → lunes anterior; jueves/viernes → lunes siguiente (Ley 27.399)
TRASLADABLES = [(6, 17, "Paso a la Inmortalidad de Güemes"), (8, 17, "Paso a la Inmortalidad de San Martín"),
                (10, 12, "Día del Respeto a la Diversidad Cultural"), (11, 20, "Día de la Soberanía Nacional")]


def _pascua(anio):
    """Domingo de Pascua (algoritmo de Gauss/Meeus)."""
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(anio, mes, dia)


def respaldo(anio):
    out = [(date(anio, m, d), n) for m, d, n in FIJOS]
    p = _pascua(anio)
    out += [(p - timedelta(days=48), "Carnaval"), (p - timedelta(days=47), "Carnaval"), (p - timedelta(days=2), "Viernes Santo")]
    for m, d, n in TRASLADABLES:
        f = date(anio, m, d)
        wd = f.weekday()   # 0 lunes
        if wd in (1, 2):
            f -= timedelta(days=wd)
        elif wd in (3, 4):
            f += timedelta(days=7 - wd)
        out.append((f, n))
    return sorted(out)


def _desde_api(anio, descargar=None):
    if descargar:
        texto = descargar(anio)
    else:
        req = urllib.request.Request(URL.format(anio=anio), headers={"User-Agent": "PalermitanHost/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:   # noqa: S310 (URL fija)
            texto = r.read(500_000).decode("utf-8", errors="replace")
    datos = json.loads(texto)
    out = []
    for x in datos if isinstance(datos, list) else []:
        if not isinstance(x, dict):
            continue
        nombre = str(x.get("nombre") or x.get("motivo") or "Feriado")[:80]
        f = None
        if x.get("fecha"):
            try:
                f = date.fromisoformat(str(x["fecha"])[:10])
            except ValueError:
                f = None
        elif x.get("dia") and x.get("mes"):
            try:
                f = date(anio, int(x["mes"]), int(x["dia"]))
            except (ValueError, TypeError):
                f = None
        if f and f.year == anio:
            tipo = str(x.get("tipo") or "")
            out.append((f, nombre + (" (puente turístico)" if "puente" in tipo.lower() else "")))
    if len(out) < 8:   # algo raro: menos feriados que los fijos
        raise ValueError("respuesta incompleta")
    return sorted(out)


def del_anio(anio, descargar=None):
    """[(fecha, nombre)] y de dónde salió ('oficial' o 'respaldo')."""
    clave = f"feriados_{anio}"
    fila = db.query_one("SELECT valor FROM config WHERE clave=%s", (clave,))
    guardado = None
    if fila and fila["valor"]:
        try:
            guardado = json.loads(fila["valor"])
        except ValueError:
            guardado = None
    if guardado and guardado.get("lista"):
        org = guardado.get("origen") or "oficial"
        # si la última vez no hubo conexión, se reintenta al día siguiente (no en cada página)
        plazo = timedelta(days=RENOVAR_DIAS if org == "oficial" else 1)
        try:
            viejo = datetime.now(timezone.utc) - datetime.fromisoformat(guardado["cuando"]) > plazo
        except (ValueError, KeyError, TypeError):
            viejo = True
        if not viejo:
            return [(date.fromisoformat(f), n) for f, n in guardado["lista"]], org
    try:
        lista = _desde_api(anio, descargar)
        db.execute("""INSERT INTO config (clave, valor) VALUES (%s, %s)
                      ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor""",
                   (clave, json.dumps({"cuando": datetime.now(timezone.utc).isoformat(), "origen": "oficial",
                                       "lista": [(f.isoformat(), n) for f, n in lista]}, ensure_ascii=False)))
        return lista, "oficial"
    except Exception as e:
        print(f"[feriados] sin conexión con la fuente ({e}); uso el respaldo")
        if guardado and guardado.get("lista") and (guardado.get("origen") or "oficial") == "oficial":
            # mejor una copia vieja de la fuente que el respaldo; se reintenta mañana
            guardado["cuando"] = (datetime.now(timezone.utc) - timedelta(days=RENOVAR_DIAS - 1)).isoformat()
            lista, org = [(date.fromisoformat(f), n) for f, n in guardado["lista"]], "oficial"
        else:
            guardado = {"cuando": datetime.now(timezone.utc).isoformat(), "origen": "respaldo",
                        "lista": [(f.isoformat(), n) for f, n in respaldo(anio)]}
            lista, org = respaldo(anio), "respaldo"
        db.execute("""INSERT INTO config (clave, valor) VALUES (%s, %s)
                      ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor""",
                   (clave, json.dumps(guardado, ensure_ascii=False)))
        return lista, org


def proximos(hoy, dias=90, descargar=None):
    """Feriados y eventos entre hoy y hoy+dias: [{desde, hasta, nombre, tipo, impacto, origen}]."""
    fin = hoy + timedelta(days=dias)
    out, origen = [], "oficial"
    for anio in sorted({hoy.year, fin.year}):
        lista, org = del_anio(anio, descargar)
        if org == "respaldo":
            origen = "respaldo"
        for f, n in lista:
            if hoy <= f <= fin:
                out.append({"desde": f, "hasta": f, "nombre": n, "tipo": "feriado", "impacto": 10, "origen": org, "id": None})
    for e in db.query("SELECT * FROM eventos WHERE hasta >= %s AND desde <= %s ORDER BY desde",
                      (hoy.isoformat(), fin.isoformat())):
        try:
            out.append({"desde": date.fromisoformat(e["desde"]), "hasta": date.fromisoformat(e["hasta"]),
                        "nombre": e["nombre"], "tipo": "evento", "impacto": int(e["impacto"] or 0),
                        "origen": "cargado por vos", "id": e["id"]})
        except ValueError:
            continue
    return sorted(out, key=lambda x: x["desde"]), origen


def noches_especiales(lista):
    """{fecha_noche: (nombre, impacto)}. Un feriado sube la noche ANTERIOR y la del feriado
    (es cuando la gente viaja); si cae lunes o viernes, todo el fin de semana largo."""
    out = {}
    for x in lista:
        if x["tipo"] == "feriado":
            f = x["desde"]
            noches = [f - timedelta(days=1), f]
            if f.weekday() == 0:      # lunes: finde largo sáb-dom-lun
                noches = [f - timedelta(days=2), f - timedelta(days=1), f]
            elif f.weekday() == 4:    # viernes: jue-vie-sáb
                noches = [f - timedelta(days=1), f, f + timedelta(days=1)]
            for n in noches:
                out.setdefault(n, (x["nombre"], x["impacto"]))
        else:
            d = x["desde"]
            while d <= x["hasta"]:
                if d not in out or out[d][1] < x["impacto"]:
                    out[d] = (x["nombre"], x["impacto"])
                d += timedelta(days=1)
    return out
