# diagnostico_serpapi.py
# ### CAMBIO AQUÍ ### — Archivo nuevo: prueba la búsqueda de Google (alquileres vacacionales) vía SerpApi.
# Gasta 1 búsqueda de las 250 gratis del mes. NO usa Groq.
# Uso:  python diagnostico_serpapi.py      → pegale a Claude todo lo que muestre.

import os
import sys

from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("DATABASE_URL", "postgresql://no-se-usa/en-esta-prueba")
KEY = os.getenv("SERPAPI_API_KEY")
if not KEY:
    sys.exit("Falta SERPAPI_API_KEY en el archivo .env")

import competencia_ia as ci

PROP = {"id": 1, "nombre": "Depto de prueba", "barrio": "Palermo", "tipo": "depto",
        "ambientes": 2, "capacidad": 4, "precio_base": 120, "moneda": "USD"}

print("=" * 70)
antes = ci.serpapi_busquedas_restantes(KEY)
print(f"Búsquedas disponibles antes: {antes if antes is not None else 'no se pudo consultar'}")

# ### CAMBIO AQUÍ ### ahora usa la búsqueda completa (hasta 2 páginas, precio de las ofertas si falta)
try:
    comps, info = ci._buscar_serpapi(PROP, KEY)   # 1 búsqueda (2 si hace falta la 2ª página)
    props, params = info["crudos"], info["params"]
except Exception as e:
    sys.exit(f"ERROR: {e}")

print(f"Consulta: {params['q']} · {params['check_in_date']} a {params['check_out_date']} · "
      f"{params['adults']} adultos · dormitorios mín.: {params.get('bedrooms', 0)} · moneda {params['currency']}")
print(f"→ {len(props)} resultados de Google en {info['busquedas']} búsqueda(s)")
for i, p in enumerate(props[:8]):
    precio = ci._precio_serpapi(p, 2)
    fuentes = ", ".join(o.get("source", "?") for o in (p.get("prices") or [])[:3])
    print(f"  [{i}] {p.get('type')} · {p.get('name', '')[:55]} · {precio} · {fuentes}")
    print(f"       {' · '.join(p.get('essential_info') or [])[:110]}")

sin_precio = [p for p in props if not ci._precio_serpapi(p, 2)]
if sin_precio:
    p = sin_precio[0]
    print(f"  Ejemplo sin precio: claves={sorted(p.keys())}")
    print(f"     ofertas={[ {k: o.get(k) for k in ('source', 'rate_per_night')} for o in (p.get('prices') or [])[:2] ]}")
stats = ci.calcular_stats(comps, "USD", None)
print("=" * 70)
print("RESUMEN")
print(f"  Resultados: {len(props)} en {info['busquedas']} búsqueda(s) · con precio por noche válido: {len(comps)}")
plataformas = {}
for c in comps:
    plataformas[c["plataforma"]] = plataformas.get(c["plataforma"], 0) + 1
print(f"  Plataformas: {plataformas}")
if stats:
    print(f"  Mediana US$ {stats['mediana']} · mínimo US$ {stats['minimo']} · máximo US$ {stats['maximo']}")
despues = ci.serpapi_busquedas_restantes(KEY)
print(f"  Búsquedas disponibles después: {despues if despues is not None else 'no se pudo consultar'}")
