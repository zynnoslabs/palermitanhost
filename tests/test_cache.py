# ### CAMBIO AQUÍ ### PRUEBA AUTOMÁTICA — ¡BORRA LA BASE QUE USA!
# Solo corre con PRUEBAS_OK=1 y una base local (PRUEBAS_DATABASE_URL en localhost). Nunca la de Render o Neon.
import os as _os, sys as _sys
from urllib.parse import urlsplit as _us
_U = _os.environ.get("PRUEBAS_DATABASE_URL", "")
if not _U or (_us(_U).hostname or "") not in ("", "localhost", "127.0.0.1") or _os.environ.get("PRUEBAS_OK") != "1":
    _sys.exit("Estas pruebas BORRAN la base: solo corren con PRUEBAS_OK=1 y PRUEBAS_DATABASE_URL apuntando a una base local.")
import os, sys, time, warnings
from datetime import date, timedelta
warnings.filterwarnings("ignore"); sys.path.insert(0, sys.argv[1])
os.environ.update(DATABASE_URL=_U, GROQ_API_KEY="x", SECRET_KEY="clave-de-prueba-larga-123", ADMIN_USER="adriano", ADMIN_PASS="prueba-segura-123",
                  SENTRY_DSN="https://abc123@o0.ingest.sentry.io/0")
import psycopg2
c0 = psycopg2.connect(os.environ["DATABASE_URL"]); c0.autocommit = True
c0.cursor().execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"); c0.close()
import app as A, database as db
F = 0
def chk(n, ok, x=""):
    global F; F += not ok; print(("OK " if ok else "XX ") + n, "" if ok else x)
hoy = date.today(); D = lambda n: (hoy + timedelta(days=n)).isoformat()
chk("con SENTRY_DSN el sistema arranca igual", A.app is not None)
c = A.app.test_client(); c.post("/login", data={"usuario": "adriano", "password": "prueba-segura-123"})
P = db.execute("INSERT INTO propiedades (nombre,barrio,precio_base,estado,moneda,ciudad) VALUES ('Soho','Palermo',50000,'activa','ARS','BA') RETURNING id")
A._datos_cambiaron()
llamadas = [0]; orig = A._analisis_estrategia_calcular
def contar(*a, **k):
    llamadas[0] += 1; return orig(*a, **k)
A._analisis_estrategia_calcular = contar
h1 = c.get("/hoy").get_data(as_text=True); h2 = c.get("/hoy").get_data(as_text=True)
chk("la segunda vez no recalcula (caché)", llamadas[0] == 1, llamadas[0])
chk("y muestra lo mismo", h1.count('class="accion"') == h2.count('class="accion"'))
import re
clave = re.search(r'name="clave" value="([^"]+)"><input type="hidden" name="estado" value="descartado"', h2)
chk("hay una tarea para descartar", clave is not None)
c.post("/acciones/estado", data={"clave": clave.group(1), "estado": "descartado", "volver": "/hoy"})
h3 = c.get("/hoy").get_data(as_text=True)
chk("después de un cambio recalcula", llamadas[0] == 2, llamadas[0])
chk("la tarea descartada ya no aparece", clave.group(1) not in h3)
db.execute("UPDATE propiedades SET precio_base=60000 WHERE id=%s", (P,))
c.get("/hoy"); chk("si cambia la propiedad recalcula aunque sea por fuera", llamadas[0] == 3, llamadas[0])
# el filtro de Sentry no manda datos personales
ev = {"request": {"cookies": {"session": "x"}, "data": {"password": "y"}, "headers": {"Cookie": "z"}, "url": "/hoy"}, "user": {"ip": "1"}}
import sentry_sdk
filtro = sentry_sdk.get_client().options.get("before_send")
r = filtro(ev, {}) if filtro else None
chk("Sentry: saca cookies, formularios, encabezados y usuario", r and "cookies" not in r["request"] and "data" not in r["request"] and "headers" not in r["request"] and "user" not in r and r["request"]["url"] == "/hoy", r)
print("FALLAS", F)
