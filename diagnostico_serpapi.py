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

try:
    props, params = ci._serpapi(PROP, KEY)
except Exception as e:
    sys.exit(f"ERROR: {e}")

print(f"Consulta: {params['q']} · {params['check_in_date']} a {params['check_out_date']} · "
      f"{params['adults']} adultos · dormitorios mín.: {params.get('bedrooms', 0)} · moneda {params['currency']}")
print(f"→ {len(props)} resultados de Google")
for i, p in enumerate(props[:8]):
    precio = (p.get("rate_per_night") or {}).get("lowest")
    fuentes = ", ".join(o.get("source", "?") for o in (p.get("prices") or [])[:3])
    print(f"  [{i}] {p.get('type')} · {p.get('name', '')[:55]} · {precio} · {fuentes}")
    print(f"       {' · '.join(p.get('essential_info') or [])[:110]}")

comps = ci.convertir_serpapi(props, PROP, params)
stats = ci.calcular_stats(comps, "USD", None)
print("=" * 70)
print("RESUMEN")
print(f"  Resultados: {len(props)} · con precio por noche válido: {len(comps)}")
plataformas = {}
for c in comps:
    plataformas[c["plataforma"]] = plataformas.get(c["plataforma"], 0) + 1
print(f"  Plataformas: {plataformas}")
if stats:
    print(f"  Mediana US$ {stats['mediana']} · mínimo US$ {stats['minimo']} · máximo US$ {stats['maximo']}")
despues = ci.serpapi_busquedas_restantes(KEY)
print(f"  Búsquedas disponibles después: {despues if despues is not None else 'no se pudo consultar'}")
