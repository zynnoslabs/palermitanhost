"""
scraper.py — Scraper de precios Airbnb (búsqueda pública, sin cuenta)
Jerarquía de fallback:
  1. Scraping en vivo de Airbnb
  2. Último resultado cacheado en DB (tabla config)
  3. Precios de referencia hardcodeados (último recurso, avisa claramente)
"""
import requests
import json
import re
import statistics
from datetime import datetime, timedelta, date

PALERMO_COORDS = {
    "ne_lat": -34.570, "ne_lng": -58.410,
    "sw_lat": -34.608, "sw_lng": -58.456,
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

TIPO_VIVIENDA_MAP = {
    "departamento": "apartments",
    "depto": "apartments",
    "casa": "houses",
    "habitacion": "private_rooms",
}


def scrape_precios_zona(
    barrio="Palermo",
    tipo_vivienda="departamento",
    ambientes=1,
    fecha_desde=None,
    noches=2,
    propiedad_id=None,
    db=None,
):
    """
    Scrapes Airbnb public search for prices in a zone.
    Fallback: cache en DB → hardcoded de referencia (con aviso).
    Retorna dict con price stats, metadata y 'error_detalle' si algo falló.
    """
    # ### CAMBIO AQUÍ ### — normalizar fecha_desde: acepta str o datetime
    if fecha_desde is None:
        dt_desde = datetime.now() + timedelta(days=7)
    elif isinstance(fecha_desde, str):
        try:
            dt_desde = datetime.strptime(fecha_desde, "%Y-%m-%d")
        except ValueError:
            dt_desde = datetime.now() + timedelta(days=7)
    elif isinstance(fecha_desde, date) and not isinstance(fecha_desde, datetime):
        dt_desde = datetime.combine(fecha_desde, datetime.min.time())
    else:
        dt_desde = fecha_desde

    dt_hasta  = dt_desde + timedelta(days=noches)
    check_in  = dt_desde.strftime("%Y-%m-%d")
    check_out = dt_hasta.strftime("%Y-%m-%d")
    tipo_map  = TIPO_VIVIENDA_MAP.get(tipo_vivienda.lower(), "apartments")

    params = {
        "query":    f"{barrio}, Buenos Aires, Argentina",
        "checkin":  check_in,
        "checkout": check_out,
        "adults":   max(ambientes, 1),
        "ne_lat": PALERMO_COORDS["ne_lat"], "ne_lng": PALERMO_COORDS["ne_lng"],
        "sw_lat": PALERMO_COORDS["sw_lat"], "sw_lng": PALERMO_COORDS["sw_lng"],
        "zoom_level": 14,
        "search_type": "user_map_move",
        "room_types[]": tipo_map,
    }
    url = "https://www.airbnb.com/s/Palermo--Buenos-Aires--Argentina/homes"

    # ── Intento 1: scraping en vivo ──────────────────────────────────────────
    error_detalle = None
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        precios, ratings = _extraer_datos(resp.text)

        if not precios:
            error_detalle = (
                f"Scraping completado pero sin precios extraíbles. "
                f"HTTP {resp.status_code}. Posible cambio en la estructura HTML de Airbnb. "
                f"Código de error: ERR-SCR-004"
            )
        else:
            precios_filtrados = _filtrar_outliers(precios)
            url_verificacion = (
                url + "?query=" + params["query"].replace(" ", "+")
                + f"&checkin={check_in}&checkout={check_out}"
            )
            return {
                "ok": True,
                "fuente": "Airbnb (scraping en vivo)",
                "precios": precios_filtrados,
                "mediana":  round(statistics.median(precios_filtrados), 2),
                "promedio": round(statistics.mean(precios_filtrados), 2),
                "min": min(precios_filtrados),
                "max": max(precios_filtrados),
                "rating_promedio_zona": (
                    round(statistics.mean(ratings), 2) if ratings else 4.5
                ),
                "cantidad_propiedades": len(precios_filtrados),
                "timestamp": datetime.now().isoformat(),
                "url_verificacion": url_verificacion,
                "error_detalle": None,
            }

    except requests.exceptions.Timeout:
        error_detalle = "Timeout: Airbnb tardó más de 15s (ERR-SCR-001)"
    except requests.exceptions.ConnectionError as e:
        error_detalle = f"Error de conexión a Airbnb: {e} (ERR-SCR-002)"
    except requests.exceptions.HTTPError as e:
        cod = e.response.status_code if e.response else "?"
        error_detalle = f"Airbnb devolvió HTTP {cod}: {e} (ERR-SCR-003)"
    except Exception as e:
        error_detalle = f"Error inesperado: {type(e).__name__}: {e} (ERR-SCR-005)"

    # ── Intento 2: último cache en DB ────────────────────────────────────────
    # ### CAMBIO AQUÍ ### — usa db.query_one() del módulo, no db.cursor()
    if db is not None and propiedad_id is not None:
        cached = _cargar_cache(db, propiedad_id)
        if cached:
            cached["fuente"] = "Datos cacheados (último scraping exitoso)"
            ts = cached.get("timestamp", "fecha desconocida")
            if isinstance(ts, str):
                ts = ts[:10]
            cached["error_detalle"] = (
                f"⚠️ No se pudo actualizar. Mostrando datos del {ts}. "
                f"Error original: {error_detalle}"
            )
            cached["ok"] = True
            return cached

    # ── Intento 3: hardcoded de referencia (último recurso) ──────────────────
    resultado = _referencia_hardcoded(barrio, tipo_vivienda, ambientes)
    resultado["error_detalle"] = (
        f"⚠️ FALLA DE SCRAPING — precios de referencia fijos (no actualizados). "
        f"Error: {error_detalle}. Pasale este código a tu desarrollador."
    )
    resultado["fuente"] = "Referencia fija (scraping y cache fallaron)"
    return resultado


# ── Extracción ────────────────────────────────────────────────────────────────

def _extraer_datos(html_text):
    precios, ratings = [], []

    match = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        html_text, re.DOTALL
    )
    if match:
        try:
            data = json.loads(match.group(1))
            listings = _buscar_listings(data)
            for item in listings:
                p = _extraer_precio(item)
                r = _extraer_rating(item)
                if p: precios.append(p)
                if r: ratings.append(r)
        except Exception:
            pass

    if not precios:
        for m in re.findall(r'"\$\s*([\d,\.]+)"', html_text):
            try:
                val = float(m.replace(".", "").replace(",", "."))
                if 1000 < val < 500000:
                    precios.append(val)
            except Exception:
                pass

    return precios, ratings


def _buscar_listings(data, depth=0):
    if depth > 8: return []
    if isinstance(data, list):
        r = []
        for item in data: r.extend(_buscar_listings(item, depth+1))
        return r
    if isinstance(data, dict):
        if "listing" in data and "price" in str(data): return [data]
        r = []
        for v in data.values(): r.extend(_buscar_listings(v, depth+1))
        return r
    return []


def _extraer_precio(item):
    try:
        s = str(item)
        for m in re.findall(r'(?:price|rate|amount)["\s:]+\$?\s*([\d]+)', s, re.I):
            val = float(m)
            if 1000 < val < 500000: return val
    except Exception: pass
    return None


def _extraer_rating(item):
    try:
        for m in re.findall(r'"rating":\s*([\d\.]+)', str(item)):
            val = float(m)
            if 1 <= val <= 5: return val
    except Exception: pass
    return None


def _filtrar_outliers(precios):
    if len(precios) < 4: return precios
    s = sorted(precios)
    n = len(s)
    q1, q3 = s[n//4], s[(3*n)//4]
    iqr = q3 - q1
    return [p for p in precios if q1 - 1.5*iqr <= p <= q3 + 1.5*iqr]


# ── Cache ─────────────────────────────────────────────────────────────────────

def _cargar_cache(db, propiedad_id):
    """
    Carga cache usando db.query_one() del módulo database.
    db aquí es el MÓDULO database, no una conexión directa.
    """
    try:
        row = db.query_one(
            "SELECT valor FROM config WHERE clave = %s",
            (f"precio_cache_{propiedad_id}",)
        )
        if row:
            return json.loads(row["valor"])
    except Exception:
        pass
    return None


# ── Referencia hardcoded (último recurso) ─────────────────────────────────────

def _referencia_hardcoded(barrio, tipo_vivienda, ambientes):
    ref = {
        ("Palermo", "departamento", 1): (18000, 25000, 35000, 4.6),
        ("Palermo", "depto",        1): (18000, 25000, 35000, 4.6),
        ("Palermo", "departamento", 2): (25000, 35000, 50000, 4.7),
        ("Palermo", "depto",        2): (25000, 35000, 50000, 4.7),
        ("Palermo", "departamento", 3): (35000, 50000, 70000, 4.5),
        ("Palermo", "casa",         2): (40000, 58000, 80000, 4.8),
        ("Palermo", "habitacion",   1): (8000,  12000, 18000, 4.4),
    }
    amb = min(ambientes or 1, 3)
    key = (barrio, tipo_vivienda.lower(), amb)
    mn, med, mx, rating = ref.get(key, (20000, 30000, 45000, 4.5))
    return {
        "ok": True,
        "precios": [mn, mn*1.1, med*0.95, med, med*1.05, mx*0.9, mx],
        "mediana":  med,
        "promedio": round((mn + med + mx) / 3, 2),
        "min": mn, "max": mx,
        "rating_promedio_zona": rating,
        "cantidad_propiedades": 0,
        "timestamp": datetime.now().isoformat(),
        "url_verificacion": "https://www.airbnb.com.ar/s/Palermo--Buenos-Aires/homes",
    }
