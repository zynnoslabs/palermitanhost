# ### CAMBIO AQUÍ ### PRUEBA AUTOMÁTICA — ¡BORRA LA BASE QUE USA!
# Solo corre con PRUEBAS_OK=1 y una base local (PRUEBAS_DATABASE_URL en localhost). Nunca la de Render o Neon.
import os as _os, sys as _sys
from urllib.parse import urlsplit as _us
_U = _os.environ.get("PRUEBAS_DATABASE_URL", "")
if not _U or (_us(_U).hostname or "") not in ("", "localhost", "127.0.0.1") or _os.environ.get("PRUEBAS_OK") != "1":
    _sys.exit("Estas pruebas BORRAN la base: solo corren con PRUEBAS_OK=1 y PRUEBAS_DATABASE_URL apuntando a una base local.")
import os, sys, warnings, re
warnings.filterwarnings("ignore"); sys.path.insert(0, sys.argv[1])
os.environ.update(DATABASE_URL=_U, GROQ_API_KEY="x", SECRET_KEY="clave-de-prueba-larga-123", ADMIN_USER="adriano", ADMIN_PASS="prueba-segura-123", TAREAS_TOKEN="token-de-prueba-largo-123")
import psycopg2
c0 = psycopg2.connect(os.environ["DATABASE_URL"]); c0.autocommit = True
c0.cursor().execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"); c0.close()
import app as A, database as db
F = 0
def chk(n, ok, x=""):
    global F; F += not ok; print(("OK " if ok else "XX ") + n, "" if ok else x)
c = A.app.test_client()
# 1) sin login no se ve nada
rutas = [r.rule for r in A.app.url_map.iter_rules() if "<" not in r.rule and r.endpoint != "static"]
publicas = {"/login", "/logout", "/salud", "/tareas/competencia", "/tipo-cambio", "/moneda", "/sw.js", "/tareas/resumen"}   # sw.js: código público de la app instalable, sin datos
abiertas = []
for r in rutas:
    if r in publicas: continue
    for m in ("GET", "POST"):
        resp = c.open(r, method=m)
        if resp.status_code == 200: abiertas.append((m, r))
chk(f"sin login: ninguna de {len(rutas)} rutas responde datos", not abiertas, abiertas)
chk("tipo de cambio sin login no se guarda", c.post("/tipo-cambio", data={"valor": "1"}).status_code in (302, 401, 403))
chk("tarea nocturna sin token: 403", c.get("/tareas/competencia").status_code == 403 and c.get("/tareas/competencia?token=x").status_code == 403)
# 2) redirecciones abiertas
def login(cli, volver=None):
    if volver:
        with cli.session_transaction() as s: s["volver_a"] = volver
    return cli.post("/login", data={"usuario": "adriano", "password": "prueba-segura-123"})
for mal in ["//evil.com", "/\\evil.com", "/\\/evil.com", "https://evil.com", "/%0d%0aevil", "\\\\evil.com"]:
    cli = A.app.test_client(); r = login(cli, mal)
    L = r.headers.get("Location", ""); chk(f"login no redirige a {mal!r}", A.destino_interno(L) or L.endswith("/hoy"), L)
cli = A.app.test_client(); r = login(cli, "/calendario?vista=linea")
chk("login sí vuelve a una página interna", r.headers.get("Location", "").endswith("/calendario?vista=linea"))
c2 = A.app.test_client(); login(c2)
for mal in ["//evil.com", "/\\evil.com", "https://evil.com/x"]:
    r = c2.post("/acciones/estado", data={"clave": "1:x", "estado": "descartado", "volver": mal})
    chk(f"'volver' no sale del sitio ({mal!r})", "evil" not in r.headers.get("Location", ""), r.headers.get("Location"))
r = c2.get("/moneda/USD", headers={"Referer": "https://evil.com/robar"})
chk("cambiar moneda no vuelve a otro sitio", "evil" not in r.headers.get("Location", ""), r.headers.get("Location"))
r = c2.get("/moneda/USD", headers={"Referer": "http://localhost/precios?x=1"})
chk("cambiar moneda vuelve a la página interna", r.headers.get("Location", "").endswith("/precios?x=1"), r.headers.get("Location"))
# 3) cabeceras
r = c2.get("/hoy")
h = r.headers
chk("CSP, nosniff, sin iframes", "frame-ancestors 'none'" in h.get("Content-Security-Policy", "") and h.get("X-Content-Type-Options") == "nosniff" and h.get("X-Frame-Options") == "DENY")
chk("páginas con datos no se guardan en caché", h.get("Cache-Control") == "no-store" and "Cookie" in h.get("Vary", ""))
chk("cookie de sesión HttpOnly y SameSite", all(x in (A.app.config["SESSION_COOKIE_HTTPONLY"], A.app.config["SESSION_COOKIE_SAMESITE"]) for x in (True, "Lax")))
# 4) XSS en lo nuevo
P = db.execute("INSERT INTO propiedades (nombre,barrio,precio_base,estado,moneda,ciudad) VALUES ('<script>alert(1)</script>','P',50000,'activa','ARS','BA') RETURNING id")
db.execute("""INSERT INTO reservas (propiedad_id,codigo_confirmacion,huesped_nombre,fecha_inicio,fecha_fin,noches,estado,ingreso_bruto,ingreso_neto,moneda)
              VALUES (%s,'X1','<img src=x onerror=alert(1)> Z',CURRENT_DATE::text,(CURRENT_DATE+3)::text,3,'confirmada',150000,120000,'ARS')""", (P,))
for u in ("/calendario?vista=linea", "/calendario?vista=mes", "/hoy", "/precios", "/ajustes"):
    t = c2.get(u).text
    chk(f"XSS escapado en {u}", "<script>alert(1)" not in t and "<img src=x" not in t)
chk("calendario 'desde' con basura", c2.get("/calendario?vista=linea&desde=<script>").status_code == 200)
chk("vista inventada se ignora", c2.get("/calendario?vista=<x>").status_code == 200)
# 5) fuerza bruta
c3 = A.app.test_client(); codes = [c3.post("/login", data={"usuario": "adriano", "password": f"mal{i}"}).status_code for i in range(6)]
chk("login se bloquea tras 5 intentos", codes[-1] == 429, codes)
chk("bloqueado aunque ponga la clave bien", c3.post("/login", data={"usuario": "adriano", "password": "prueba-segura-123"}).status_code == 429)
# 6) SQL
r = c2.get("/calendario?vista=linea&propiedad_id=1%20OR%201=1"); chk("propiedad_id con SQL no rompe", r.status_code == 200)
print("FALLAS", F)
