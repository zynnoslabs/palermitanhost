# ### CAMBIO AQUÍ ### PRUEBA AUTOMÁTICA — ¡BORRA LA BASE QUE USA!
# Solo corre con PRUEBAS_OK=1 y una base local (PRUEBAS_DATABASE_URL en localhost). Nunca la de Render o Neon.
import os as _os, sys as _sys
from urllib.parse import urlsplit as _us
_U = _os.environ.get("PRUEBAS_DATABASE_URL", "")
if not _U or (_us(_U).hostname or "") not in ("", "localhost", "127.0.0.1") or _os.environ.get("PRUEBAS_OK") != "1":
    _sys.exit("Estas pruebas BORRAN la base: solo corren con PRUEBAS_OK=1 y PRUEBAS_DATABASE_URL apuntando a una base local.")
import os, sys, json, warnings
warnings.filterwarnings("ignore"); sys.path.insert(0, sys.argv[1])
os.environ.update(DATABASE_URL=_U, GROQ_API_KEY="x",
                  SECRET_KEY="clave-de-prueba-larga-123", ADMIN_USER="adriano", ADMIN_PASS="prueba-segura-123", TAREAS_TOKEN="z"*20)
import psycopg2
c0 = psycopg2.connect(os.environ["DATABASE_URL"]); c0.autocommit = True
c0.cursor().execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"); c0.close()
import app as A, database as db, ia, competencia_ia as ci
fallas = 0
def chk(n, c, x=""):
    global fallas
    if not c: fallas += 1
    print(("OK " if c else "XX ") + n, "" if c else x)
X = '<script>alert(1)</script><img src=x onerror=alert(2)>"\'><svg onload=alert(3)>'
c = A.app.test_client(); c.post("/login", data={"usuario": "adriano", "password": "prueba-segura-123"})
# propiedad con payloads en todos los campos de texto
c.post("/propiedades/nueva", data={"nombre": "P"+X, "direccion": X, "barrio": "Palermo", "tipo": "depto", "ambientes": 2,
       "capacidad": 4, "estado": "activa", "moneda": "USD", "precio_base": 100, "info_huespedes": X, "rating": 4.8, "reviews_count": 10})
pid = db.query_one("SELECT id FROM propiedades")["id"]
db.execute("""INSERT INTO reservas (propiedad_id,codigo_confirmacion,huesped_nombre,fecha_inicio,fecha_fin,noches,ingreso_bruto,ingreso_neto,estado,moneda)
              VALUES (%s,%s,%s,'2030-01-01','2030-01-03',2,200,190,'confirmada','USD')""", (pid, "HM"+X, X))
# competidor manual con link javascript: y competidor de "internet" con link javascript:
c.post(f"/competencia?pid={pid}", data={"barrio": "Palermo", "tipo": "depto", "precio_noche": "120", "moneda": "USD",
       "plataforma": X, "titulo": X, "zona": X, "link": "javascript:alert(document.cookie)", "notas": X})
db.execute("""INSERT INTO competencia (propiedad_id,barrio,precio_noche,fecha,plataforma,titulo,zona,link,origen,moneda)
              VALUES (%s,'Palermo',110,'2030-01-01',%s,%s,%s,'JavaScript:alert(9)','ia','USD')""", (pid, X, X, X))
chk("link javascript: no se guarda en la carga manual", db.query_one("SELECT link FROM competencia WHERE origen='manual'")["link"] == "")
chk("limpiar_comparables descarta javascript:", ci.limpiar_comparables([{"link": "javascript:alert(1)", "precio_noche": 100, "moneda": "USD"}]) == [])
db.execute("INSERT INTO config (clave,valor) VALUES (%s,%s)", (f"competencia_resumen_{pid}", json.dumps({"texto": X, "fecha": X, "fuente": X})))
db.execute("INSERT INTO config (clave,valor) VALUES ('competencia_ultima_corrida',%s)", (json.dumps({"inicio": X, "ok": 1, "grupos": 1, "errores": [X], "terminado": True}),))
# IA que devuelve código malicioso
class R:
    def __init__(s, t): s.choices = [type('C', (), {'message': type('M', (), {'content': t})()})()]; s.usage = None
ia.completar = lambda *a, **k: R(X)
c.post("/asistente", data={"propiedad_id": pid, "mensaje": X})
c.post("/resenas/nueva", data={"propiedad_id": pid, "huesped": X, "puntaje": 5, "texto": X})
c.post("/asistente/chat", json={"mensaje": X})
db.execute("INSERT INTO informes (titulo,fecha_desde,fecha_hasta,contenido) VALUES (%s,%s,%s,%s)", (X, X, X, X))
db.execute("INSERT INTO config (clave,valor) VALUES ('tipo_cambio',%s) ON CONFLICT (clave) DO UPDATE SET valor=EXCLUDED.valor",
           (json.dumps({"valor": 1400, "tipo": X, "fecha": X}),))
paginas = ["/", "/?desde=2029-01-01&hasta=2031-01-01", "/propiedades", f"/propiedades/{pid}/editar", "/importar", f"/precios?propiedad_id={pid}",
           f"/competencia?pid={pid}", "/asistente?tab=negocio", "/asistente?tab=huespedes", "/asistente?tab=resenas", "/informes", "/informes/1"]
for u in paginas:
    r = c.get(u); h = r.get_data(as_text=True)
    malo = [m for m in ("<script>alert", "<img src=x", "<svg onload", 'href="javascript', "href='javascript", 'href="JavaScript') if m in h]
    chk(f"{u} sin código inyectado ({r.status_code})", r.status_code == 200 and not malo, malo)
r = c.get("/")
chk("encabezado CSP presente", "script-src 'self'" in r.headers.get("Content-Security-Policy", "") and "frame-ancestors 'none'" in r.headers["Content-Security-Policy"])
chk("X-Frame-Options y nosniff", r.headers.get("X-Frame-Options") == "DENY" and r.headers.get("X-Content-Type-Options") == "nosniff")
print("\nFALLAS:", fallas)
