# competencia_ia.py
# ### CAMBIO AQUÍ ### — Archivo nuevo.
# Busca en internet propiedades similares a las de Adriano usando Groq con
# búsqueda web incorporada (herramienta "browser_search", modelos openai/gpt-oss).
# NO hace scraping: la IA usa un buscador web y devuelve lo que encontró.
#
# ### CAMBIO AQUÍ ### — Estrategia de búsqueda: varias fuentes EN CADENA (si una falla, sigue la otra)
#   1. Google Hotels → "alquileres vacacionales" vía SerpApi (serpapi.com): precio REAL por noche
#      para fechas concretas, de Airbnb, VRBO, Booking... No usa IA ni tokens de Groq.
#      Plan gratis: 250 búsquedas por mes (1 por barrio por noche alcanza de sobra).
#   2. Tavily (api.tavily.com): 1 crédito por búsqueda, fragmentos cortos con precio.
#      La IA (modelo rápido de Groq) solo ordena esos fragmentos: pocos tokens.
#   3. Respaldo: búsqueda web de Groq (browser_search). Lee páginas enteras: gasta MUCHOS tokens.
#   Nuestro servidor nunca entra a Airbnb: no hay IP nuestra que bloquear.
#
# Variables de entorno:
#   SERPAPI_API_KEY           (recomendada: fuente principal)
#   SERPAPI_DIAS_ADELANTE     (opcional, default 14: para qué fecha se piden los precios)
#   SERPAPI_NOCHES            (opcional, default 2: noches de la estadía de referencia)
#   GROQ_API_KEY              (obligatoria, la misma que ya usa ia.py)
#   TAVILY_API_KEY            (recomendada; segunda fuente)
#   TAVILY_MAX_BUSQUEDAS      (opcional, default 2: 1 crédito cada una)
#   COMPETENCIA_RESPALDO_GROQ (opcional, "1" por defecto; "0" para no usar nunca el respaldo caro)
#   GROQ_SEARCH_MODEL         (opcional, default "openai/gpt-oss-120b")
# ### CAMBIO AQUÍ ### — cada anuncio guarda su moneda (ARS o USD). Las estadísticas se
# calculan en la moneda de la propiedad usando el tipo de cambio del sistema (monedas.py).

import os
import re
import json
import statistics
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

import requests
from groq import Groq

import monedas   # ### CAMBIO AQUÍ ###
import ia

SEARCH_MODEL = os.getenv("GROQ_SEARCH_MODEL", "openai/gpt-oss-120b")
RESUMEN_MODEL = os.getenv("GROQ_MODEL_RAPIDO", "openai/gpt-oss-20b")   # ### CAMBIO AQUÍ ### modelo rápido
MIN_COMPARABLES = 3
# ### CAMBIO AQUÍ ### — sin Zonaprop/Argenprop: ahí "temporario" es alquiler POR MES, no por noche
# ### CAMBIO AQUÍ ### — sin MercadoLibre: en el diagnóstico solo trajo alquileres mensuales y ventas
DOMINIOS = ["airbnb.com.ar", "airbnb.com", "booking.com", "vrbo.com", "despegar.com.ar"]
RE_NOCHE = re.compile(r"\b(noche|noches|night|nights|nightly|por d[ií]a|diario)\b")
RE_OTRA_MONEDA = re.compile(r"(r\$|\bmxn\b|\bbrl\b|€|\beur\b|\bclp\b|\buyu\b|\bcop\b|£|\bmx\$)")
RE_MES = re.compile(r"\b(mes|meses|mensual|mensuales|month|monthly|expensas|contrato)\b")
# Tope razonable de precio POR NOCHE (más que esto casi seguro es un precio mensual)
TOPE_NOCHE = {"USD": (15, 500), "ARS": (15000, 700000)}
PLATAFORMAS = {"airbnb": "Airbnb", "booking": "Booking", "vrbo": "VRBO", "zonaprop": "Zonaprop",
               "argenprop": "Argenprop", "mercadolibre": "MercadoLibre"}


def _cliente():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY no configurada en .env")
    return Groq(api_key=api_key, timeout=90)


def _prompt(prop):
    barrio = prop.get("barrio") or "Palermo"
    tipo = prop.get("tipo") or "departamento"
    amb = prop.get("ambientes") or "?"
    cap = prop.get("capacidad") or "?"
    return f"""Buscá en internet anuncios ACTUALES de alquiler temporario en Buenos Aires, Argentina,
parecidos a esta propiedad:
- Barrio: {barrio}
- Tipo: {tipo}
- Ambientes: {amb}
- Capacidad: {cap} huéspedes

Buscá en varias plataformas (Airbnb, Booking.com, VRBO, Zonaprop temporarios, Argenprop, etc.).
Quiero entre 6 y 10 anuncios del mismo barrio o barrios vecinos, con cantidad de ambientes y
capacidad parecidas.

LÍMITE DE BÚSQUEDA (### CAMBIO AQUÍ ### para no gastar el cupo de la IA):
- Hacé como máximo 3 búsquedas. Usá los resultados y listados que ya traen precio;
  no abras anuncios uno por uno. Si con eso no llegás a 6, devolvé los que tengas.

REGLAS IMPORTANTES:
1. Solo incluí anuncios que realmente encontraste, con su link real. No inventes nada.
2. Si un dato no aparece, poné null. No lo adivines.
3. "zona" es la ubicación aproximada que muestra el anuncio (ej: "Palermo Soho, cerca de Plaza Serrano").
   Las plataformas no muestran la dirección exacta; no la inventes.
4. "precio_noche" es el precio por noche (número, sin puntos ni símbolos) y "moneda" es "ARS" o "USD".

Respondé ÚNICAMENTE con un JSON válido, sin texto antes ni después, con este formato:
{{"comparables": [
  {{"plataforma": "Airbnb", "titulo": "...", "zona": "...", "ambientes": 2, "capacidad": 4,
    "precio_noche": 55000, "moneda": "ARS", "rating": 4.8, "link": "https://..."}}
]}}"""


def _extraer_json(texto):
    """Saca el primer objeto JSON del texto de la IA (a veces viene con ```json)."""
    if not texto:
        return None
    texto = re.sub(r"```(?:json)?", "", texto)
    # ### CAMBIO AQUÍ ### — más robusto: busca el objeto que contiene "comparables"
    # (la IA a veces agrega texto o citas con llaves antes o después del JSON)
    dec = json.JSONDecoder()
    candidatos = [m.start() for m in re.finditer(r"\{", texto)]
    for i in candidatos:
        try:
            obj, _ = dec.raw_decode(texto[i:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "comparables" in obj:
            return obj
    return None


def _a_numero(valor):
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    limpio = re.sub(r"[^\d,\.]", "", str(valor))
    if not limpio:
        return None
    # "55.000" o "55,000" -> 55000 ; "4,8" -> 4.8
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", limpio):
        limpio = re.sub(r"[.,]", "", limpio)
    else:
        limpio = limpio.replace(",", ".")
    try:
        return float(limpio)
    except ValueError:
        return None


def limpiar_comparables(crudos):
    """
    Valida lo que devolvió la IA. Descarta filas sin link o sin precio.
    Cada anuncio conserva su moneda original (ARS o USD).
    """
    limpios, links_vistos = [], set()
    for c in crudos or []:
        if not isinstance(c, dict):
            continue
        link = str(c.get("link") or "").strip()
        if not link.startswith("http") or link in links_vistos:
            continue
        precio = _a_numero(c.get("precio_noche"))
        if not precio or precio <= 0:
            continue
        # ### CAMBIO AQUÍ ### — si dice otra moneda (reales, pesos mexicanos, euros...) se descarta
        if c.get("moneda") and not monedas.normalizar(c.get("moneda")):
            continue
        moneda = monedas.normalizar(c.get("moneda"), "ARS")
        # Filtro de cordura: precios por noche absurdos (ej. precio mensual)
        if moneda == "ARS" and not (5000 <= precio <= 3000000):
            continue
        if moneda == "USD" and not (10 <= precio <= 2000):
            continue
        rating = _a_numero(c.get("rating"))
        if rating is not None and not (1 <= rating <= 5):
            rating = None
        amb = _a_numero(c.get("ambientes"))
        cap = _a_numero(c.get("capacidad"))
        links_vistos.add(link)
        limpios.append({
            "plataforma": str(c.get("plataforma") or "Web")[:40],
            "titulo": str(c.get("titulo") or "")[:150],
            "zona": str(c.get("zona") or "")[:150],
            "ambientes": int(amb) if amb else None,
            "capacidad": int(cap) if cap else None,
            "precio_noche": float(precio),
            "moneda": moneda,
            "rating": rating,
            "link": link[:500],
            "nota": "",
        })
    return limpios


def calcular_stats(comparables, a_moneda="ARS", tc=None):
    """Mediana, mínimo y máximo en la moneda pedida. Omite los que no se pueden convertir."""
    precios = []
    for c in comparables:
        v = monedas.convertir(c.get("precio_noche"), c.get("moneda") or "ARS", a_moneda, tc)
        if v:
            precios.append(v)
    ratings = [c["rating"] for c in comparables if c.get("rating")]
    if not precios:
        return None
    return {
        "cantidad": len(precios),
        "mediana": round(statistics.median(precios), 2),
        "minimo": round(min(precios), 2),
        "maximo": round(max(precios), 2),
        "rating": round(statistics.mean(ratings), 2) if ratings else None,
        "moneda": a_moneda,
        "sin_convertir": len([c for c in comparables if c.get("precio_noche")]) - len(precios),
    }


def _resumen_ia(prop, stats):
    """Pide a Groq un resumen corto. Si falla, arma uno simple sin IA."""
    precio_base = prop.get("precio_base") or 0
    mon = stats["moneda"]
    texto_base = (
        f"Mercado: {stats['cantidad']} anuncios similares, mediana {monedas.formatear(stats['mediana'], mon)} "
        f"por noche (rango {monedas.formatear(stats['minimo'], mon)} a {monedas.formatear(stats['maximo'], mon)})."
    )
    try:
        prompt = f"""Sos asesor de alquileres temporarios en Buenos Aires. Escribí en español rioplatense,
con voseo, un resumen de máximo 4 oraciones para el dueño de "{prop.get('nombre')}".
Datos de la competencia encontrada hoy (todo en {mon}): {stats['cantidad']} anuncios similares,
mediana {stats['mediana']} por noche, mínimo {stats['minimo']}, máximo {stats['maximo']}.
Precio actual del dueño: {precio_base} {mon} por noche.
Decile si está por encima o por debajo del mercado y una recomendación concreta.
Usá solo estos números, no inventes otros."""
        r = ia.completar([{"role": "user", "content": prompt}], RESUMEN_MODEL, 1200, 0.3)
        return ia.texto_respuesta(r)
    except Exception:
        return texto_base


# ════════════ ### CAMBIO AQUÍ ### TAVILY ════════════
def _consultas_tavily(prop):
    # ### CAMBIO AQUÍ ### — las 2 variantes que mejor funcionaron en el diagnóstico (A y C).
    # Agregar ambientes o capacidad a la consulta dio 0 precios por noche.
    barrio = prop.get("barrio") or "Palermo"
    return [
        f"departamento por noche {barrio} Buenos Aires",
        f"{barrio} Buenos Aires apartment price per night",
    ]


def _plataforma(url):
    host = urlparse(url).netloc.lower()
    for clave, nombre in PLATAFORMAS.items():
        if clave in host:
            return nombre
    return host.replace("www.", "")[:30] or "Web"


def _tavily(consulta, api_key):
    r = requests.post(
        "https://api.tavily.com/search",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"query": consulta, "search_depth": "basic", "max_results": 20,
              "include_domains": DOMINIOS, "topic": "general"},   # ### CAMBIO AQUÍ ### sin "country": daba 0 resultados
        timeout=30,
    )
    if r.status_code in (401, 403):
        raise RuntimeError("La clave de Tavily (TAVILY_API_KEY) es inválida.")
    if r.status_code in (429, 432, 433):
        raise RuntimeError("Se terminaron los créditos de Tavily de este mes.")
    r.raise_for_status()
    return r.json().get("results") or []


def _prompt_extraer(prop, resultados):
    bloques = []
    for i, r in enumerate(resultados):
        bloques.append(f"[{i}] {r.get('title', '')}\nURL: {r.get('url', '')}\n{(r.get('content') or '')[:700]}")
    return f"""Estos son resultados de búsqueda de alquileres temporarios en Buenos Aires.
Propiedad a comparar: {prop.get('ambientes') or '?'} ambientes, {prop.get('capacidad') or '?'} huéspedes,
barrio {prop.get('barrio') or '?'}.

Elegí SOLO los resultados que muestran un precio POR NOCHE de un alojamiento parecido (mismo barrio
o vecino). OJO: en Argentina "alquiler temporario" suele ser POR MES (ej: "USD 800 + expensas"); esos NO van.
No inventes nada: si un dato no está en el texto, poné null.
En "texto_precio" copiá EXACTAMENTE el pedazo del resultado donde aparece el precio (palabra por palabra).

RESULTADOS:
{chr(10).join(bloques)}

Respondé ÚNICAMENTE con JSON, con el número de resultado en "i":
{{"comparables": [{{"i": 0, "titulo": "...", "zona": "...", "ambientes": 2, "capacidad": 4,
  "precio_noche": 55000, "moneda": "ARS", "rating": 4.8, "texto_precio": "$ 55.000 por noche"}}]}}"""


def _norm_txt(t):
    return re.sub(r"\s+", " ", (t or "").lower()).strip()


def periodo_verificado(c, r):
    """
    ### CAMBIO AQUÍ ### — no confía en la IA: verifica en el texto real del resultado que el
    precio aparezca y que diga "por noche". Devuelve "noche", "mes" o None (dudoso → se descarta).
    """
    fuente = _norm_txt((r.get("title") or "") + " " + (r.get("content") or ""))
    tp = _norm_txt(c.get("texto_precio"))
    precio = _a_numero(c.get("precio_noche"))
    if not tp or not precio or tp not in fuente:
        return None
    # ### CAMBIO AQUÍ ### — Booking/Airbnb a veces muestran la versión de otro país (R$, MXN, €)
    if RE_OTRA_MONEDA.search(tp) or (c.get("moneda") and not monedas.normalizar(c.get("moneda"))):
        return "otra_moneda"
    digitos_tp = re.sub(r"\D", "", tp)
    if str(int(precio)) not in digitos_tp:
        return None
    pos = fuente.find(tp)
    ventana = fuente[max(0, pos - 40): pos + len(tp) + 40]
    if RE_MES.search(ventana):
        return "mes"
    mon = monedas.normalizar(c.get("moneda"), "ARS")
    lo, hi = TOPE_NOCHE[mon]
    if not (lo <= precio <= hi):
        return "mes" if precio > hi else None
    # "por noche" cerca del precio, o en el título del resultado (ej: "Alojamiento por noche")
    if RE_NOCHE.search(ventana) or RE_NOCHE.search(_norm_txt(r.get("title"))):
        return "noche"
    return None


def _buscar_tavily(prop, api_key):
    """Devuelve (comparables, info) usando Tavily + modelo rápido de Groq."""
    max_busq = int(os.getenv("TAVILY_MAX_BUSQUEDAS", "2") or 2)
    comparables, creditos, tokens, vistos, total_res, mensuales, dudosos = [], 0, 0, set(), 0, 0, 0
    for consulta in _consultas_tavily(prop)[:max_busq]:
        resultados = [r for r in _tavily(consulta, api_key) if r.get("url") and r["url"] not in vistos]
        creditos += 1
        total_res += len(resultados)
        if not resultados:
            continue
        vistos.update(r["url"] for r in resultados)
        resp = ia.completar([{"role": "user", "content": _prompt_extraer(prop, resultados)}],
                            ia.GROQ_MODEL_RAPIDO, 3000, 0.1)
        tokens += getattr(getattr(resp, "usage", None), "total_tokens", 0) or 0
        data = _extraer_json(resp.choices[0].message.content or "") or {}
        crudos = []
        for c in data.get("comparables") or []:
            try:
                r = resultados[int(c.get("i"))]
            except (TypeError, ValueError, IndexError):
                continue
            periodo = periodo_verificado(c, r)
            if periodo != "noche":
                if periodo == "mes":
                    mensuales += 1
                else:
                    dudosos += 1   # dudoso u otra moneda
                continue
            # El link SIEMPRE sale del resultado real de Tavily (la IA no puede inventarlo)
            c["link"] = r["url"]
            c["plataforma"] = _plataforma(r["url"])
            c["titulo"] = c.get("titulo") or r.get("title", "")
            crudos.append(c)
        comparables = limpiar_comparables(comparables + crudos)
        if len(comparables) >= 6:
            break
    return comparables, {"creditos": creditos, "tokens": tokens, "resultados": total_res,
                         "mensuales": mensuales, "dudosos": dudosos}


# ════════════ ### CAMBIO AQUÍ ### FUENTE 1: GOOGLE (alquileres vacacionales) vía SerpApi ════════════
SERPAPI_URL = "https://serpapi.com/search.json"
FUENTES_SERPAPI = {"airbnb": "Airbnb", "vrbo": "VRBO", "booking": "Booking", "expedia": "Expedia",
                   "despegar": "Despegar", "hotels.com": "Hotels.com"}
RE_DORM = re.compile(r"(\d+)\s*(bedroom|dormitorio|habitaci[oó]n|cuarto)", re.I)
RE_CAPAC = re.compile(r"(?:sleeps|capacidad para|hasta|para)\s*(\d+)|(\d+)\s*(?:guests|huéspedes|huespedes|personas)", re.I)
RE_ESTUDIO = re.compile(r"\b(studio|estudio|monoambiente)\b", re.I)


def _fechas_serpapi():
    dias = int(os.getenv("SERPAPI_DIAS_ADELANTE", "14") or 14)
    noches = int(os.getenv("SERPAPI_NOCHES", "2") or 2)
    entrada = datetime.now(timezone(timedelta(hours=-3))).date() + timedelta(days=dias)
    return entrada.isoformat(), (entrada + timedelta(days=noches)).isoformat()


def serpapi_busquedas_restantes(api_key):
    """Consulta gratis (no gasta búsquedas). Devuelve el número o None si no se pudo saber."""
    try:
        r = requests.get("https://serpapi.com/account.json", params={"api_key": api_key}, timeout=15)
        if r.status_code != 200:
            return None
        d = r.json()
        v = d.get("total_searches_left", d.get("plan_searches_left"))
        return int(v) if v is not None else None
    except Exception:
        return None


def _precio_serpapi(p, noches):
    """### CAMBIO AQUÍ ### Precio por noche: el principal; si no viene, el más bajo de las ofertas
    (Vrbo, Expedia...); si tampoco, el total de la estadía dividido por las noches."""
    v = (p.get("rate_per_night") or {}).get("extracted_lowest")
    if v:
        return v
    ofertas = [(o.get("rate_per_night") or {}).get("extracted_lowest") for o in p.get("prices") or []]
    ofertas = [x for x in ofertas if isinstance(x, (int, float)) and x > 0]
    if ofertas:
        return min(ofertas)
    total = (p.get("total_rate") or {}).get("extracted_lowest")
    if isinstance(total, (int, float)) and total > 0 and noches:
        return round(total / noches, 2)
    return None


def _serpapi(prop, api_key, page_token=None):
    barrio = prop.get("barrio") or "Palermo"
    entrada, salida = _fechas_serpapi()
    amb = prop.get("ambientes") or 0
    params = {
        "engine": "google_hotels", "vacation_rentals": "true",
        "q": f"{barrio}, Buenos Aires, Argentina",
        "check_in_date": entrada, "check_out_date": salida,
        "adults": max(int(prop.get("capacidad") or 2), 1),
        "currency": prop.get("moneda") or "USD", "gl": "ar", "hl": "es",
        "api_key": api_key,
    }
    if amb and int(amb) > 1:
        params["bedrooms"] = int(amb) - 1   # 2 ambientes = 1 dormitorio
    if page_token:
        params["next_page_token"] = page_token   # ### CAMBIO AQUÍ ### segunda página
    r = requests.get(SERPAPI_URL, params=params, timeout=60)
    try:
        data = r.json()
    except Exception:
        data = {}
    err = (data.get("error") or "") if isinstance(data, dict) else ""
    if r.status_code == 401 or "invalid api key" in err.lower():
        raise RuntimeError("La clave de SerpApi (SERPAPI_API_KEY) es inválida.")
    if r.status_code == 429 or "run out of searches" in err.lower():
        raise RuntimeError("Se terminaron las búsquedas de SerpApi de este mes.")
    if err:
        if "hasn't returned any results" in err.lower():
            return [], params
        raise RuntimeError(f"SerpApi: {err}")
    r.raise_for_status()
    params["_siguiente"] = (data.get("serpapi_pagination") or {}).get("next_page_token")
    return data.get("properties") or [], params


def _plataforma_serpapi(p):
    for oferta in p.get("prices") or []:
        src = (oferta.get("source") or "").lower()
        for clave, nombre in FUENTES_SERPAPI.items():
            if clave in src:
                return nombre
    if p.get("link"):
        return _plataforma(p["link"])
    return "Google"


def convertir_serpapi(props, prop, params):
    """Pasa los resultados de Google al formato de comparables (sin IA)."""
    mon = params.get("currency", "USD")
    barrio = prop.get("barrio") or ""
    try:
        noches = (date.fromisoformat(params["check_out_date"]) - date.fromisoformat(params["check_in_date"])).days
    except Exception:
        noches = None
    crudos = []
    for p in props or []:
        if (p.get("type") or "").lower() not in ("vacation rental", "alquiler vacacional", ""):
            continue
        precio = _precio_serpapi(p, noches)   # ### CAMBIO AQUÍ ###
        if not precio:
            continue
        tope = TOPE_NOCHE.get(mon)   # ### CAMBIO AQUÍ ### descarta valores fuera de rango (ej. US$ 1.046)
        if tope and not (tope[0] <= precio <= tope[1]):
            continue
        info = " · ".join(p.get("essential_info") or [])
        m = RE_DORM.search(info)
        dorm = int(m.group(1)) if m else (0 if RE_ESTUDIO.search(info) else None)
        m = RE_CAPAC.search(info)
        cap = int(m.group(1) or m.group(2)) if m else None
        link = p.get("link") or ("https://www.google.com/travel/search?q=" +
                                 requests.utils.quote(f"{p.get('name', '')} {barrio} Buenos Aires"))
        crudos.append({
            "plataforma": _plataforma_serpapi(p),
            "titulo": p.get("name") or "",
            "zona": barrio,
            "ambientes": (dorm + 1) if dorm is not None else None,
            "capacidad": cap,
            "precio_noche": precio,
            "moneda": mon,
            "rating": p.get("overall_rating"),
            "link": link,
        })
    return limpiar_comparables(crudos)


def _buscar_serpapi(prop, api_key):
    """### CAMBIO AQUÍ ### Hasta SERPAPI_PAGINAS páginas (1 búsqueda cada una). Pide la 2ª solo
    si la 1ª trajo menos de SERPAPI_MIN_PRECIOS precios válidos."""
    paginas = int(os.getenv("SERPAPI_PAGINAS", "2") or 2)
    minimo = int(os.getenv("SERPAPI_MIN_PRECIOS", "10") or 10)
    todos, usadas, token, params = [], 0, None, {}
    while usadas < paginas:
        try:
            props, params = _serpapi(prop, api_key, token)
        except Exception:
            if usadas == 0:
                raise          # la 1ª falló: que la cadena pase a la siguiente fuente
            break              # la 2ª falló: nos quedamos con lo de la 1ª
        usadas += 1
        todos += props
        token = params.get("_siguiente")
        if not token or len(convertir_serpapi(todos, prop, params)) >= minimo:
            break
    return convertir_serpapi(todos, prop, params), {"resultados": len(todos), "busquedas": usadas,
                                                    "fechas": f"{params.get('check_in_date')} a {params.get('check_out_date')}",
                                                    "crudos": todos, "params": params}


def _buscar_groq(prop, resultado):
    """Respaldo: búsqueda web de Groq (gasta muchos tokens)."""
    # si el modelo grande no tiene cupo (error 429), prueba con el rápido
    modelos = [SEARCH_MODEL] + ([ia.GROQ_MODEL_RAPIDO] if ia.GROQ_MODEL_RAPIDO != SEARCH_MODEL else [])
    texto, ultimo_error = None, None
    for modelo in modelos:
        try:
            r = _cliente().chat.completions.create(
                model=modelo,
                messages=[{"role": "user", "content": _prompt(prop)}],
                tools=[{"type": "browser_search"}],
                tool_choice="required",
                temperature=0.2,
                max_tokens=8000,
                **ia.extra_modelo(modelo, "low"),   # ### CAMBIO AQUÍ ### menos vueltas = menos tokens
            )
            texto = r.choices[0].message.content or ""
            # cuántos tokens gastó la búsqueda (para controlar el cupo de Groq)
            resultado["tokens"] = (resultado.get("tokens") or 0) + (
                getattr(getattr(r, "usage", None), "total_tokens", 0) or 0)
            resultado["modelo"] = modelo
            break
        except Exception as e:
            ultimo_error = e
            if "429" not in str(e) and "rate_limit" not in str(e):
                break
    if texto is None:
        raise RuntimeError(f"{ia.explicar_error(ultimo_error)} (ERR-COMP-001)")
    data = _extraer_json(texto)
    if not data or not isinstance(data.get("comparables"), list):
        raise RuntimeError("La IA respondió en un formato inesperado. Probá de nuevo en un rato. (ERR-COMP-002)")
    return limpiar_comparables(data["comparables"])


def buscar_comparables(prop, tc=None, con_resumen=True):
    """
    prop: dict de la tabla propiedades. tc: tipo de cambio USD->ARS (o None).
    Devuelve dict: ok, comparables, stats, resumen, error, fecha, fuente, creditos_tavily, tokens.
    """
    resultado = {"ok": False, "comparables": [], "stats": None, "resumen": "", "error": None,
                 "fecha": datetime.now(timezone(timedelta(hours=-3))).date().isoformat(), "fuente": None, "creditos_tavily": 0, "tokens": 0}
    comparables, errores, fuentes = [], [], []
    resultado["busquedas_serpapi"] = 0

    # ### CAMBIO AQUÍ ### 1) Google alquileres vacacionales vía SerpApi (precios reales, sin IA)
    serp_key = os.getenv("SERPAPI_API_KEY")
    if serp_key:
        try:
            comparables, info = _buscar_serpapi(prop, serp_key)
            resultado["busquedas_serpapi"] = info["busquedas"]
            if comparables:
                fuentes.append("Google (SerpApi)")
            else:
                errores.append(f"Google: {info['resultados']} resultados, ninguno con precio por noche válido")
        except Exception as e:
            errores.append(str(e))

    # 2) Tavily (barato) solo si Google no trajo suficientes
    tavily_key = os.getenv("TAVILY_API_KEY")
    if tavily_key and len(comparables) < MIN_COMPARABLES:
        try:
            extra, info = _buscar_tavily(prop, tavily_key)
            resultado["creditos_tavily"] = info["creditos"]
            resultado["tokens"] = info["tokens"]
            if extra:
                comparables = limpiar_comparables(comparables + extra)
                fuentes.append("Tavily")
            if not extra:   # ### CAMBIO AQUÍ ### pocos resultados es normal: se acumulan día a día
                errores.append(f"Tavily: {info['resultados']} resultados, solo {len(extra)} con precio por noche "
                               f"verificado ({info['mensuales']} eran precios mensuales, {info['dudosos']} dudosos)")
        except Exception as e:
            errores.append(f"Tavily: {ia.explicar_error(e) if 'Groq' in str(e) or '429' in str(e) else e}")

    # 3) Respaldo Groq (caro) solo si nada trajo resultados
    # ### CAMBIO AQUÍ ### — apagado por defecto: gasta ~190.000 tokens y agota el cupo gratis de Groq
    if not comparables and os.getenv("COMPETENCIA_RESPALDO_GROQ", "0") == "1":
        try:
            extra = _buscar_groq(prop, resultado)
            if extra:
                comparables = limpiar_comparables(comparables + extra)
                fuentes.append("búsqueda web de Groq")
        except Exception as e:
            errores.append(str(e))

    resultado["fuente"] = " + ".join(fuentes) or None
    resultado["avisos"] = errores   # ### CAMBIO AQUÍ ### fuentes que fallaron aunque otra haya andado
    if not comparables:
        detalle = (" Detalle: " + " | ".join(errores)) if errores else ""
        resultado["error"] = "No se encontraron anuncios válidos (con link y precio). (ERR-COMP-003)" + detalle
        return resultado

    mon_prop = prop.get("moneda") or "ARS"
    resultado["ok"] = True
    resultado["comparables"] = comparables
    resultado["stats"] = calcular_stats(comparables, mon_prop, tc)
    if resultado["stats"]:
        resultado["resumen"] = _resumen_ia(prop, resultado["stats"]) if con_resumen else ""
        if resultado["stats"]["sin_convertir"]:
            resultado["resumen"] += (f"\n\n({resultado['stats']['sin_convertir']} anuncios están en otra moneda "
                                     f"y no se incluyeron: cargá el tipo de cambio arriba a la derecha.)")
    else:
        resultado["resumen"] = ("Los anuncios encontrados están en otra moneda. Cargá el tipo de cambio "
                                "(arriba a la derecha) para comparar.")
    return resultado
