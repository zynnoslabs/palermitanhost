# probar_ia.py
# ### CAMBIO AQUÍ ### — Archivo nuevo: prueba las 5 funciones de IA sin base de datos.
# Uso (en la carpeta rentaia):
#   1. Crear el archivo .env con GROQ_API_KEY=tu_clave  (no lo subas a GitHub: ya está en .gitignore)
#   2. pip install -r requirements.txt
#   3. python probar_ia.py
# Copiá lo que muestre la consola y pasáselo a Claude.

import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("DATABASE_URL", "postgresql://no-se-usa/en-esta-prueba")

if not os.getenv("GROQ_API_KEY"):
    sys.exit("Falta GROQ_API_KEY en el archivo .env")

import ia
import competencia_ia

PROP = {
    "id": 1, "nombre": "Depto de prueba", "barrio": "Palermo", "tipo": "depto",
    "ambientes": 2, "capacidad": 4, "precio_base": 120, "moneda": "USD",
}
INFO = "WiFi: CasaPalermo / Clave: 12345678\nCheck-in 14 a 22 hs. Check-out 11 hs.\nNo hay cochera."
resultados = []


def prueba(nombre, funcion):
    print(f"\n{'=' * 60}\n▶ {nombre}")
    t = time.time()
    try:
        salida = funcion()
        print(salida)
        # ### CAMBIO AQUÍ ### responder_huesped devuelve el error como texto: detectarlo
        if isinstance(salida, tuple) and str(salida[0]).startswith("Error al generar"):
            raise RuntimeError(salida[0])
        print(f"✅ OK ({time.time() - t:.1f} s)")
        resultados.append((nombre, "OK"))
    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}: {e}")
        resultados.append((nombre, f"ERROR: {e}"))


print(f"Modelo principal: {ia.GROQ_MODEL} | Modelo rápido: {ia.GROQ_MODEL_RAPIDO}")

prueba("1. Informe con IA", lambda: ia.generar_informe(
    {"total_reservas": 7, "tasa_ocupacion": 76.7, "adr": 118, "revpar": 90,
     "ingreso_bruto": 2714, "ingreso_neto_real": 1733, "moneda": "dólares (USD)"},
    nombre_propiedad=PROP["nombre"], periodo="2026-09-01 al 2026-09-30")[:600] + " …")

prueba("2. Respuesta a huésped (dato que SÍ está)", lambda: ia.responder_huesped(
    1, "Hola! Cuál es la clave del wifi?", INFO, PROP["nombre"]))

prueba("3. Respuesta a huésped (dato que NO está → pendiente)", lambda: ia.responder_huesped(
    1, "Tienen pileta?", INFO, PROP["nombre"]))

prueba("4. Respuesta a reseña", lambda: ia.responder_resena(
    "Muy lindo y bien ubicado, pero el agua caliente tardaba.", 4, PROP["nombre"]))


def _competencia():
    # ### CAMBIO AQUÍ ### — muestra qué motor se usó y cuánto gastó
    if not os.getenv("TAVILY_API_KEY"):
        print("⚠ No hay TAVILY_API_KEY en el .env: se usa solo la búsqueda de Groq (gasta mucho cupo).")
    r = competencia_ia.buscar_comparables(PROP, tc=1400)
    if not r["ok"]:
        raise RuntimeError(r["error"])
    lineas = [f"{c['plataforma']:10} | {c['moneda']} {c['precio_noche']:>10,.0f} | {c['zona'][:40]:40} | {c['link'][:60]}"
              for c in r["comparables"]]
    return ("\n".join(lineas) + f"\n\nEstadísticas: {r['stats']}\n\nResumen IA: {r['resumen']}"
            f"\n\nFuente: {r.get('fuente')} | Créditos de Tavily: {r.get('creditos_tavily')} | "
            f"Tokens de Groq: {r.get('tokens')}" + (f" (respaldo con {r.get('modelo')})" if r.get('modelo') else ""))


prueba("5. Búsqueda de competencia en internet (tarda hasta 1 min)", _competencia)

print(f"\n{'=' * 60}\nRESUMEN")
for n, estado in resultados:
    print(f"  {n}: {estado}")
