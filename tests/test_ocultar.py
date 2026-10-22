# ### CAMBIO AQUÍ ### PRUEBA AUTOMÁTICA — ¡BORRA LA BASE QUE USA!
# Solo corre con PRUEBAS_OK=1 y una base local (PRUEBAS_DATABASE_URL en localhost). Nunca la de Render o Neon.
import os as _os, sys as _sys
from urllib.parse import urlsplit as _us
_U = _os.environ.get("PRUEBAS_DATABASE_URL", "")
if not _U or (_us(_U).hostname or "") not in ("", "localhost", "127.0.0.1") or _os.environ.get("PRUEBAS_OK") != "1":
    _sys.exit("Estas pruebas BORRAN la base: solo corren con PRUEBAS_OK=1 y PRUEBAS_DATABASE_URL apuntando a una base local.")
import os, sys, warnings
from datetime import date, timedelta
warnings.filterwarnings("ignore"); sys.path.insert(0, sys.argv[1])
os.environ.update(DATABASE_URL=_U, GROQ_API_KEY="x", SECRET_KEY="clave-de-prueba-larga-123", ADMIN_USER="adriano", ADMIN_PASS="prueba-segura-123")
import app as A, database as db, alertas
F = 0
def chk(n, ok, x=""):
    global F; F += not ok; print(("OK " if ok else "XX ") + n, "" if ok else x)
c = A.app.test_client(); c.post("/login", data={"usuario": "adriano", "password": "prueba-segura-123"})
alertas.mostrar_todas()
todas = alertas.revisar(); chk("hay alertas de base", len(todas) >= 3, len(todas))
chk("claves únicas", len({a["clave"] for a in todas}) == len(todas))
chk("clave estable", [a["clave"] for a in alertas.revisar()] == [a["clave"] for a in todas])
k = todas[0]["clave"]; t0 = todas[0]["titulo"]
html = c.get("/").get_data(as_text=True)
chk("dashboard muestra la ✕", 'action="/alertas/ocultar"' in html and k in html)
r = c.post("/alertas/ocultar", data={"clave": k, "volver": "/?propiedad_id=1"})
chk("ocultar redirige a donde estaba", r.status_code == 302 and r.headers["Location"].endswith("/?propiedad_id=1"), r.headers.get("Location"))
vis, ocu = alertas.separar(alertas.revisar())
chk("ya no se ve", k not in [a["clave"] for a in vis] and len(ocu) == 1)
html = c.get("/").get_data(as_text=True)
chk("dashboard: no aparece y dice 1 ocultada", t0 not in html and "1 oculta(s)" in html)
vis8, ocu8 = alertas.separar(alertas.revisar(), date.today() + timedelta(days=8))
chk("a los 8 días vuelve", k in [a["clave"] for a in vis8] and not ocu8)
r = c.post("/alertas/ocultar", data={"clave": k, "volver": "https://malo.com"})
chk("volver externo bloqueado", r.headers["Location"].endswith("/"), r.headers["Location"])
r = c.post("/alertas/ocultar", data={"clave": k, "volver": "//malo.com"})
chk("volver // bloqueado", "malo" not in r.headers["Location"])
db.execute("UPDATE config SET valor='basura{' WHERE clave='alertas_ocultas'")
chk("config rota no rompe", c.get("/").status_code == 200 and len(alertas.separar(alertas.revisar())[0]) == len(todas))
c.post("/alertas/ocultar", data={"clave": "x" * 100})
chk("clave gigante ignorada", "x" * 100 not in (db.query_one("SELECT valor FROM config WHERE clave='alertas_ocultas'")["valor"] or ""))
c.post("/alertas/ocultar", data={"clave": k}); c.post("/alertas/mostrar", data={})
chk("mostrar de nuevo", len(alertas.separar(alertas.revisar())[0]) == len(todas))
c2 = A.app.test_client(); r = c2.post("/alertas/ocultar", data={"clave": k})
chk("sin login no deja", r.status_code == 302 and "login" in r.headers["Location"])
chk("sin ocultas: no muestra el cartel", "oculta(s)" not in c.get("/").get_data(as_text=True))
print("FALLAS", F)
