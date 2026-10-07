# diagnostico_tavily.py
# ### CAMBIO AQUÍ ### — prueba VARIAS formas de buscar en Tavily y muestra cuál trae
# precios por noche verificados. Gasta ~5 créditos de Tavily y pocos tokens de Groq.
# Uso:  python diagnostico_tavily.py      → pegale a Claude todo lo que muestre.

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("DATABASE_URL", "postgresql://no-se-usa/en-esta-prueba")
KEY = os.getenv("TAVILY_API_KEY")
if not KEY:
    sys.exit("Falta TAVILY_API_KEY en el archivo .env")

import ia
import competencia_ia as ci

PROP = {"id": 1, "nombre": "Depto de prueba", "barrio": "Palermo", "tipo": "depto",
        "ambientes": 2, "capacidad": 4, "precio_base": 120, "moneda": "USD"}

DOM_ESTADIAS = ["airbnb.com.ar", "airbnb.com", "booking.com", "vrbo.com", "despegar.com.ar",
                "mercadolibre.com.ar"]

VARIANTES = [
    ("A. corta + sitios de estadías", "departamento por noche Palermo Buenos Aires", DOM_ESTADIAS, None),
    ("B. 2 ambientes + sitios de estadías", "departamento 2 ambientes Palermo Buenos Aires precio por noche", DOM_ESTADIAS, None),
    ("C. en inglés + sitios", "Palermo Buenos Aires apartment price per night", DOM_ESTADIAS, None),
    ("D. solo Despegar (promedios por noche)", "precio por noche departamento Palermo", ["despegar.com.ar"], None),
    ("E. solo MercadoLibre", "alojamiento por noche Palermo 2 ambientes", ["mercadolibre.com.ar"], None),
]

def buscar(consulta, dominios, pais):
    cuerpo = {"query": consulta, "search_depth": "basic", "max_results": 20}
    if dominios:
        cuerpo["include_domains"] = dominios
    if pais:
        cuerpo["country"] = pais
    r = requests.post("https://api.tavily.com/search", headers={"Authorization": f"Bearer {KEY}"},
                      json=cuerpo, timeout=30)
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}: {r.text[:200]}"
    return r.json().get("results") or [], None


resumen = []
for nombre, consulta, dominios, pais in VARIANTES:
    print("=" * 70)
    print(f"{nombre}\n  consulta: {consulta}\n  sitios: {dominios or 'todos'} · país: {pais or 'todos'}")
    resultados, error = buscar(consulta, dominios, pais)
    if error:
        print(f"  ❌ {error}")
        resumen.append((nombre, "error", 0))
        continue
    print(f"  → {len(resultados)} resultados")
    for i, r in enumerate(resultados[:8]):
        texto = (r.get("content") or "").replace("\n", " ")
        print(f"   [{i}] {r.get('url', '')[:95]}\n        {texto[:220]}")
    noche = 0
    if resultados:
        try:
            resp = ia.completar([{"role": "user", "content": ci._prompt_extraer(PROP, resultados)}],
                                ia.GROQ_MODEL_RAPIDO, 3000, 0.1)
        except Exception as e:   # ### CAMBIO AQUÍ ### sin cupo de Groq: sigue con la próxima variante
            print(f"  ⚠ Groq no pudo analizar: {ia.explicar_error(e)}")
            resumen.append((nombre, len(resultados), "?"))
            continue
        data = ci._extraer_json(resp.choices[0].message.content or "") or {}
        for c in data.get("comparables") or []:
            try:
                r = resultados[int(c.get("i"))]
            except (TypeError, ValueError, IndexError):
                continue
            p = ci.periodo_verificado(c, r)
            marca = {"noche": "✅ por noche", "mes": "❌ mensual", "otra_moneda": "❌ otra moneda"}.get(p, "❌ dudoso")
            print(f"   precio [{c.get('i')}] {c.get('moneda')} {c.get('precio_noche')} · \"{c.get('texto_precio')}\" → {marca}")
            noche += p == "noche"
    resumen.append((nombre, len(resultados), noche))

print("\n" + "=" * 70 + "\nRESUMEN (resultados · precios por noche verificados)")
for nombre, n, noche in resumen:
    print(f"  {nombre}: {n} resultados · {noche} por noche")
