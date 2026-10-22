# ### CAMBIO AQUÍ ### PRUEBA AUTOMÁTICA — ¡BORRA LA BASE QUE USA!
# Solo corre con PRUEBAS_OK=1 y una base local (PRUEBAS_DATABASE_URL en localhost). Nunca la de Render o Neon.
import os as _os, sys as _sys
from urllib.parse import urlsplit as _us
_U = _os.environ.get("PRUEBAS_DATABASE_URL", "")
if not _U or (_us(_U).hostname or "") not in ("", "localhost", "127.0.0.1") or _os.environ.get("PRUEBAS_OK") != "1":
    _sys.exit("Estas pruebas BORRAN la base: solo corren con PRUEBAS_OK=1 y PRUEBAS_DATABASE_URL apuntando a una base local.")
import os, sys, io, re, warnings
warnings.filterwarnings("ignore"); sys.path.insert(0, sys.argv[1])
os.environ.update(DATABASE_URL=_U, GROQ_API_KEY="x", SECRET_KEY="clave-de-prueba-larga-123", ADMIN_USER="adriano", ADMIN_PASS="prueba-segura-123")
import psycopg2
c0 = psycopg2.connect(os.environ["DATABASE_URL"]); c0.autocommit = True
c0.cursor().execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"); c0.close()
import app as A, database as db, ia, asistente_route as AR
F = 0
def chk(n, ok, x=""):
    global F; F += not ok; print(("OK " if ok else "XX ") + n, "" if ok else x)
c = A.app.test_client(); c.post("/login", data={"usuario": "adriano", "password": "prueba-segura-123"})
txt = open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "datos", "Prueba_Precio_Airbnb.csv"), encoding="utf-8").read().replace("Huésped 7,", "Carla Gómez,")
r1 = c.post("/importar", data={"csv_file": (io.BytesIO(txt.encode()), "x.csv")}, content_type="multipart/form-data")
h = c.get(r1.headers["Location"]).text; t = re.search(r'name="t" value="([^"]+)"', h).group(1)
c.post("/importar/asignar", data={"asignar": "1", "t": t, "prop_0": "nueva"})
db.execute("UPDATE propiedades SET recambio_limpieza=25000, recambio_insumos=12000, estadia_minima=7, barrio='Palermo'")
db.execute("INSERT INTO comentarios (clave, texto) VALUES ('1:precios', 'Ojo que Carla Gómez pagó aparte 20.000')")
enviado = {}
def falso(messages, *a, **k):
    enviado["m"] = messages
    return "x"
ia.completar = falso
ia.texto_respuesta = lambda r: "## Cuadro\n| Duración | Te queda |\n|---|---|\n| 4 a 6 noches | $ 40.000 |\n\n- listo"
r = c.post("/asistente/chat", json={"mensaje": "¿qué hago hoy?"}).get_json()
sp = enviado["m"][0]["content"]
chk("la IA recibe la estrategia", "ESTRATEGIA" in sp and "Costo por recambio: $ 37.000" in sp and "Acciones pendientes" in sp, sp[-1500:])
chk("la IA recibe el comentario de Adriano", "pagó aparte 20.000" in sp)
chk("sin nombres de huéspedes en lo que se manda", "Carla Gómez" not in str(enviado["m"]))
chk("respuesta con tabla en HTML", "<table" in r.get("html", "") and "<th>Duración</th>" in r["html"], r)
chk("historial muestra la tabla", "<table" in c.get("/asistente").text)
print("   largo del contexto:", len(sp), "caracteres")
print("FALLAS", F)
