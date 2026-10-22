# ### CAMBIO AQUÍ ### PRUEBA AUTOMÁTICA — ¡BORRA LA BASE QUE USA!
# Solo corre con PRUEBAS_OK=1 y una base local (PRUEBAS_DATABASE_URL en localhost). Nunca la de Render o Neon.
import os as _os, sys as _sys
from urllib.parse import urlsplit as _us
_U = _os.environ.get("PRUEBAS_DATABASE_URL", "")
if not _U or (_us(_U).hostname or "") not in ("", "localhost", "127.0.0.1") or _os.environ.get("PRUEBAS_OK") != "1":
    _sys.exit("Estas pruebas BORRAN la base: solo corren con PRUEBAS_OK=1 y PRUEBAS_DATABASE_URL apuntando a una base local.")
import os, sys, warnings
warnings.filterwarnings("ignore"); sys.path.insert(0, sys.argv[1])
os.environ.update(DATABASE_URL=_U, GROQ_API_KEY="x", SECRET_KEY="clave-de-prueba-larga-123", ADMIN_USER="adriano", ADMIN_PASS="prueba-segura-123")
os.environ.pop("PERMITIR_BORRAR_TODO", None)
import app as A, database as db
F = 0
def chk(n, ok, x=""):
    global F; F += not ok; print(("OK " if ok else "XX ") + n, "" if ok else x)
cnt = lambda t: db.query_one(f"SELECT COUNT(*) AS n FROM {t}")["n"]
c = A.app.test_client(); c.post("/login", data={"usuario": "adriano", "password": "prueba-segura-123"})
p0 = cnt("propiedades"); chk("hay datos de prueba", p0 > 0 and cnt("reservas") > 0)
chk("sin la variable: no existe (404)", c.get("/borrar-todo").status_code == 404 and c.post("/borrar-todo", data={"frase":"BORRAR TODO","password":"prueba-segura-123"}).status_code == 404)
chk("sin la variable: no borró", cnt("propiedades") == p0)
os.environ["PERMITIR_BORRAR_TODO"] = "si"
h = c.get("/borrar-todo"); chk("con la variable: muestra la página", h.status_code == 200 and "no se puede deshacer" in h.get_data(as_text=True))
c.post("/borrar-todo", data={"frase": "borrar", "password": "prueba-segura-123"}); chk("frase mal: no borra", cnt("propiedades") == p0)
c.post("/borrar-todo", data={"frase": "BORRAR TODO", "password": "mal"}); chk("clave mal: no borra", cnt("propiedades") == p0)
c2 = A.app.test_client(); r = c2.post("/borrar-todo", data={"frase": "BORRAR TODO", "password": "prueba-segura-123"})
chk("sin login: no borra", r.status_code == 302 and cnt("propiedades") == p0)
r = c.post("/borrar-todo", data={"frase": "borrar todo ", "password": "prueba-segura-123"}, follow_redirects=True)
html = r.get_data(as_text=True)
chk("borra todo", all(cnt(t) == 0 for t in ["propiedades","reservas","movimientos_airbnb","reservas_historial","competencia","resenas","consultas_huespedes","informes"]) and cnt("temporadas") == 12)
chk("dashboard abre vacío y sigue logueado", r.status_code == 200 and "quedó vacío" in html, r.status_code)
chk("config inicial repuesta", db.query_one("SELECT valor FROM config WHERE clave='chat_huespedes'") is not None)
for u in ["/", "/propiedades", "/calendario", "/importar", "/precios", "/informes", "/competencia", "/asistente", "/asistente?tab=huespedes", "/asistente?tab=resenas", "/salud?db=1"]:
    chk("vacío abre " + u, c.get(u).status_code == 200, c.get(u).status_code)
pid = db.execute("INSERT INTO propiedades (nombre,barrio,precio_base,estado,moneda) VALUES ('Nueva','Palermo',1,'activa','ARS') RETURNING id")
chk("ids vuelven a empezar en 1", pid == 1, pid)
print("FALLAS", F)
