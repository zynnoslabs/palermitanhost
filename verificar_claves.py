# verificar_claves.py
# ### CAMBIO AQUÍ ### — Archivo nuevo: revisa el archivo de claves ANTES de cargarlo en Render.
#
# Uso (dentro de rentaia):   python verificar_claves.py
#   (por defecto lee ..\CLAVES_ADRIANO.env; otro archivo: python verificar_claves.py RUTA)
#
# Qué hace:
#   1. Genera SECRET_KEY y TAREAS_TOKEN si están vacías (y las guarda en el archivo).
#   2. Revisa que no falte nada y que cada clave tenga el formato correcto.
#   3. Prueba cada servicio de verdad (Groq, SerpApi, Tavily, base de datos).
#      Gasta 1 crédito de Tavily (de 1.000). Groq y SerpApi: gratis.
#   4. Crea CLAVES_PARA_RENDER.env (sin comentarios ni vacíos) para pegar en Render → "Add from .env".
# Nunca muestra las claves completas en pantalla.

import os
import re
import sys
import secrets

import requests

try:   # en Windows, para que los íconos ✅ ❌ se vean bien
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RUTA = sys.argv[1] if len(sys.argv) > 1 else os.path.join("..", "CLAVES_ADRIANO.env")
GENERADAS = {"SECRET_KEY": 32, "TAREAS_TOKEN": 24}
problemas, avisos = [], []


def ok(msg):
    print(f"  ✅ {msg}")


def mal(msg):
    problemas.append(msg)
    print(f"  ❌ {msg}")


def ojo(msg):
    avisos.append(msg)
    print(f"  ⚠  {msg}")


def oculto(v):
    return (v[:4] + "…" + v[-3:]) if len(v) > 10 else "…"


# ── 1. Leer el archivo (y completar las claves que se generan solas) ──────────
if not os.path.exists(RUTA):
    sys.exit(f"No encuentro el archivo {os.path.abspath(RUTA)}")
with open(RUTA, encoding="utf-8") as f:
    lineas = f.read().splitlines()

valores, cambio = {}, False
for i, linea in enumerate(lineas):
    m = re.match(r"^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$", linea)
    if not m:
        continue
    clave, valor = m.group(1), m.group(2).strip().strip('"').strip("'")
    if clave in GENERADAS and (not valor or valor.startswith(("inventar", "cambiar"))):   # ### CAMBIO AQUÍ ### el valor de ejemplo no sirve
        valor = secrets.token_hex(GENERADAS[clave])
        lineas[i] = f"{clave}={valor}"
        cambio = True
        print(f"  🔑 {clave} generada automáticamente")
    valores[clave] = valor
if cambio:
    with open(RUTA, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")

v = valores.get
print("=" * 70)
print("1) REVISIÓN DE FORMATO")

# ── 2. Formato ─────────────────────────────────────────────────────────────────
db_url = v("DATABASE_URL") or ""
if not db_url:
    mal("DATABASE_URL vacía (Render → base de datos → Connect → Internal Database URL)")
elif not db_url.startswith(("postgres://", "postgresql://")):
    mal("DATABASE_URL no parece una dirección de Postgres (debe empezar con postgresql://)")
else:
    ok("DATABASE_URL con formato correcto")

if len(v("ADMIN_USER") or "") < 3:
    mal("ADMIN_USER: mínimo 3 caracteres")
else:
    ok(f"ADMIN_USER = {v('ADMIN_USER')}")
clave_admin = v("ADMIN_PASS") or ""
if len(clave_admin) < 10 or clave_admin in ("admin123", "1234567890"):
    mal("ADMIN_PASS: mínimo 10 caracteres y que no sea una clave obvia")
else:
    ok(f"ADMIN_PASS con {len(clave_admin)} caracteres")
if len(v("SECRET_KEY") or "") < 16:
    mal("SECRET_KEY: mínimo 16 caracteres (dejala vacía y se genera sola)")
else:
    ok("SECRET_KEY lista")
if len(v("TAREAS_TOKEN") or "") < 16:
    mal("TAREAS_TOKEN: mínimo 16 caracteres (dejala vacía y se genera sola)")
else:
    ok("TAREAS_TOKEN lista")

groq = v("GROQ_API_KEY") or ""
if not groq.startswith("gsk_"):
    mal("GROQ_API_KEY vacía o mal copiada (empieza con gsk_)")
serp = v("SERPAPI_API_KEY") or ""
tav = v("TAVILY_API_KEY") or ""
if tav and not tav.startswith("tvly-"):
    mal("TAVILY_API_KEY mal copiada (empieza con tvly-)")
if not serp and not tav:
    mal("Falta al menos una fuente de competencia: SERPAPI_API_KEY (principal) o TAVILY_API_KEY")
elif not serp:
    ojo("Sin SERPAPI_API_KEY: la competencia va a traer pocos datos (solo Tavily)")
elif not tav:
    ojo("Sin TAVILY_API_KEY: si Google falla no hay respaldo")

# ── 3. Pruebas reales ──────────────────────────────────────────────────────────
print("=" * 70)
print("2) PRUEBAS CON CADA SERVICIO")

if groq.startswith("gsk_"):
    try:
        r = requests.get("https://api.groq.com/openai/v1/models",
                         headers={"Authorization": f"Bearer {groq}"}, timeout=20)
        if r.status_code == 200:
            ids = {m.get("id") for m in r.json().get("data", [])}
            faltan = [m for m in (v("GROQ_MODEL"), v("GROQ_MODEL_RAPIDO")) if m and m not in ids]
            if faltan:
                mal(f"Groq: la clave anda pero estos modelos no existen: {', '.join(faltan)}")
            else:
                ok(f"Groq: clave {oculto(groq)} válida y modelos disponibles")
        elif r.status_code == 401:
            mal("Groq: la clave es inválida")
        else:
            mal(f"Groq respondió {r.status_code}")
    except Exception as e:
        mal(f"Groq: no se pudo conectar ({e})")

if serp:
    try:
        r = requests.get("https://serpapi.com/account.json", params={"api_key": serp}, timeout=20)
        d = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code == 200 and "error" not in d:
            ok(f"SerpApi: clave {oculto(serp)} válida · {d.get('total_searches_left', '?')} búsquedas disponibles este mes")
        else:
            mal(f"SerpApi: {d.get('error') or 'clave inválida'}")
    except Exception as e:
        mal(f"SerpApi: no se pudo conectar ({e})")

if tav.startswith("tvly-"):
    try:
        r = requests.post("https://api.tavily.com/search", headers={"Authorization": f"Bearer {tav}"},
                          json={"query": "Palermo Buenos Aires", "max_results": 1, "search_depth": "basic"},
                          timeout=30)
        if r.status_code == 200:
            ok(f"Tavily: clave {oculto(tav)} válida (se usó 1 crédito)")
        elif r.status_code in (401, 403):
            mal("Tavily: la clave es inválida")
        elif r.status_code in (429, 432, 433):
            ojo("Tavily: la clave anda pero no tiene créditos este mes")
        else:
            mal(f"Tavily respondió {r.status_code}")
    except Exception as e:
        mal(f"Tavily: no se pudo conectar ({e})")

if db_url.startswith(("postgres://", "postgresql://")):
    host = re.sub(r"^.*@", "", db_url).split("/")[0].split(":")[0]
    if "." not in host:
        ok("DATABASE_URL es la dirección INTERNA de Render (correcto): solo funciona dentro de Render, "
           "por eso no se prueba desde tu compu")
    else:
        try:
            import psycopg2
            con = psycopg2.connect(db_url, connect_timeout=10)
            con.cursor().execute("SELECT 1")
            con.close()
            ok("Base de datos: conexión correcta")
            ojo("Estás usando la dirección EXTERNA: en Render conviene la INTERNA (más rápida y segura)")
        except ImportError:
            ojo("No pude probar la base (falta psycopg2 en tu compu); se prueba al arrancar en Render")
        except Exception as e:
            mal(f"Base de datos: no conecta ({str(e).strip()[:120]})")

# ── 4. Archivo limpio para Render ──────────────────────────────────────────────
print("=" * 70)
salida = os.path.join(os.path.dirname(os.path.abspath(RUTA)), "CLAVES_PARA_RENDER.env")
with open(salida, "w", encoding="utf-8") as f:
    for clave, valor in valores.items():
        if valor:
            f.write(f"{clave}={valor}\n")

if problemas:
    print(f"RESULTADO: ❌ {len(problemas)} problema(s). Corregí el archivo y volvé a correr este script.")
else:
    print("RESULTADO: ✅ TODO OK" + (f" (con {len(avisos)} aviso/s)" if avisos else ""))
    print(f"  → Render → Environment → 'Add from .env' → pegá el contenido de:\n     {salida}")
    print(f"  → Para cron-job.org, el valor de X-Token es el TAREAS_TOKEN de ese archivo.")
print("  ⚠ Ninguno de los dos archivos se sube a GitHub ni se manda por chat.")
