# ical.py
# ### CAMBIO AQUÍ ### — Archivo nuevo: lee el calendario iCal de cada anuncio de Airbnb.
#
# Airbnb da, para cada anuncio, un link de "Exportar calendario" (Calendario → Disponibilidad →
# Conectar calendarios → Exportar). Ese link dice qué noches están reservadas o bloqueadas.
# NO trae precios ni nombres: solo fechas. Es la forma oficial y permitida (no es scraping).
# Se lee como mucho una vez por hora por propiedad.

import re
import urllib.request
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

import database as db

CADA_MINUTOS = 60
TIMEOUT = 10
MAX_BYTES = 2_000_000


def url_valida(url):
    """Solo links https de Airbnb que sean de calendario iCal. Devuelve (ok, mensaje)."""
    url = (url or "").strip()
    if not url:
        return True, ""
    try:
        u = urlparse(url)
    except ValueError:
        return False, "El link del calendario no es válido."
    host = (u.hostname or "").lower()
    es_airbnb = re.fullmatch(r"(www\.)?airbnb\.[a-z]{2,3}(\.[a-z]{2})?", host) is not None
    if u.scheme != "https" or not es_airbnb or "/calendar/ical/" not in u.path:
        return False, ("El link del calendario tiene que ser el de Airbnb: empieza con https://www.airbnb… "
                       "y contiene /calendar/ical/. Lo sacás en Airbnb → Calendario → Disponibilidad → Exportar calendario.")
    return True, ""


def _fecha(valor):
    m = re.match(r"(\d{4})(\d{2})(\d{2})", valor or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def parsear(texto):
    """Devuelve [(desde, hasta, tipo)] con hasta = día de salida (no incluido)."""
    texto = re.sub(r"\r?\n[ \t]", "", texto or "")   # líneas partidas del formato iCal
    eventos = []
    for bloque in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", texto, re.S):
        campos = {}
        for linea in bloque.splitlines():
            if ":" in linea:
                k, v = linea.split(":", 1)
                campos[k.split(";")[0].strip().upper()] = v.strip()
        d1, d2 = _fecha(campos.get("DTSTART")), _fecha(campos.get("DTEND"))
        if not d1:
            continue
        if not d2 or d2 <= d1:
            d2 = d1 + timedelta(days=1)
        resumen = (campos.get("SUMMARY") or "").lower()
        tipo = "reservada" if "reserv" in resumen else "bloqueada"
        eventos.append((d1, d2, tipo))
    return eventos


def _descargar(url):
    req = urllib.request.Request(url, headers={"User-Agent": "PalermitanHost/1.0 (calendario)"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:   # noqa: S310 (url validada antes)
        datos = r.read(MAX_BYTES + 1)
    if len(datos) > MAX_BYTES:
        raise ValueError("el calendario es demasiado grande")
    return datos.decode("utf-8", errors="replace")


def _clave(pid):
    return f"ical_leido_{pid}"


def ultimo(pid):
    """(fecha y hora de la última lectura buena, error de la última lectura o '')."""
    fila = db.query_one("SELECT valor FROM config WHERE clave=%s", (_clave(pid),))
    if not fila or not fila["valor"]:
        return None, ""
    partes = fila["valor"].split("|", 1)
    try:
        cuando = datetime.fromisoformat(partes[0]) if partes[0] else None
    except ValueError:
        cuando = None
    return cuando, (partes[1] if len(partes) > 1 else "")


def actualizar(prop, forzar=False, descargar=None):
    """Lee el iCal de una propiedad si pasó más de una hora. Nunca rompe: devuelve (ok, mensaje)."""
    url = (prop.get("ical_url") or "").strip()
    if not url:
        return False, "sin link"
    ok, msg = url_valida(url)
    if not ok:
        return False, msg
    cuando, _ = ultimo(prop["id"])
    ahora = datetime.now(timezone.utc)
    if not forzar and cuando and ahora - cuando < timedelta(minutes=CADA_MINUTOS):
        return True, "reciente"
    try:
        texto = (descargar or _descargar)(url)
        if "BEGIN:VCALENDAR" not in (texto or ""):
            raise ValueError("Airbnb no devolvió un calendario (revisá el link)")
        eventos = parsear(texto)
    except Exception as e:
        error = str(e)[:150] or "no se pudo leer"
        anterior = cuando.isoformat() if cuando else ""
        db.execute("""INSERT INTO config (clave, valor) VALUES (%s, %s)
                      ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor""", (_clave(prop["id"]), f"{anterior}|{error}"))
        return False, error
    filas = [(prop["id"], d1.isoformat(), d2.isoformat(), t) for d1, d2, t in eventos]
    conn = db.get_db()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM ical_bloqueos WHERE propiedad_id=%s", (prop["id"],))
        if filas:
            cur.executemany("INSERT INTO ical_bloqueos (propiedad_id, desde, hasta, tipo) VALUES (%s,%s,%s,%s)", filas)
        cur.execute("""INSERT INTO config (clave, valor) VALUES (%s, %s)
                       ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor""", (_clave(prop["id"]), ahora.isoformat() + "|"))
        conn.commit()
        cur.close()
    except Exception:
        db._rollback(conn)
        raise
    finally:
        db._release(conn)
    return True, f"{len(filas)} períodos"


def noches_ocupadas(pid, desde, hasta):
    """Conjunto de fechas ocupadas o bloqueadas en [desde, hasta) según el último iCal leído."""
    out = set()
    for b in db.query("SELECT desde, hasta FROM ical_bloqueos WHERE propiedad_id=%s AND hasta > %s AND desde < %s",
                      (pid, desde.isoformat(), hasta.isoformat())):
        d1, d2 = date.fromisoformat(b["desde"]), date.fromisoformat(b["hasta"])
        d = max(d1, desde)
        while d < min(d2, hasta):
            out.add(d)
            d += timedelta(days=1)
    return out
