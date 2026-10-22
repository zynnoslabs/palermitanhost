# ### CAMBIO AQUÍ ### PRUEBA AUTOMÁTICA — ¡BORRA LA BASE QUE USA!
# Solo corre con PRUEBAS_OK=1 y una base local (PRUEBAS_DATABASE_URL en localhost). Nunca la de Render o Neon.
import os as _os, sys as _sys
from urllib.parse import urlsplit as _us
_U = _os.environ.get("PRUEBAS_DATABASE_URL", "")
if not _U or (_us(_U).hostname or "") not in ("", "localhost", "127.0.0.1") or _os.environ.get("PRUEBAS_OK") != "1":
    _sys.exit("Estas pruebas BORRAN la base: solo corren con PRUEBAS_OK=1 y PRUEBAS_DATABASE_URL apuntando a una base local.")
import os, sys, time, warnings
warnings.filterwarnings("ignore"); sys.path.insert(0, sys.argv[1])
os.environ.update(DATABASE_URL=_U, GROQ_API_KEY="x", SECRET_KEY="clave-de-prueba-larga-123", ADMIN_USER="adriano", ADMIN_PASS="prueba-segura-123")
import psycopg2
c0 = psycopg2.connect(os.environ["DATABASE_URL"]); c0.autocommit = True
c0.cursor().execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"); c0.close()
import app as A
F = 0
def chk(n, ok, x=""):
    global F; F += not ok; print(("OK " if ok else "XX ") + n, "" if ok else x)
def entrar():
    c = A.app.test_client(); c.post("/login", data={"usuario": "adriano", "password": A.ADMIN_PASS}); return c
adentro = lambda c: c.get("/hoy").status_code == 200
compu, celu = entrar(), entrar()
chk("compu y celular entran", adentro(compu) and adentro(celu))
compu.get("/logout"); chk("cerrar sesión en la compu no afecta al celular", not adentro(compu) and adentro(celu))
compu = entrar()
r = celu.post("/sesiones/cerrar-todas")
chk("botón: el que lo aprieta queda afuera", r.headers["Location"].endswith("/login") and not adentro(celu))
chk("botón: la compu también queda afuera", not adentro(compu))
m = compu.get("/login").get_data(as_text=True)
chk("avisa que la sesión se cerró", "Tu sesión se cerró" in m or "Volvé a ingresar" in m)
compu = entrar(); chk("después se puede volver a entrar", adentro(compu))
# cambio de contraseña
A.ADMIN_PASS = "una-clave-nueva-456"
chk("cambiar la contraseña echa a las sesiones abiertas", not adentro(compu))
chk("con la clave vieja no entra", not adentro(A.app.test_client().__class__(A.app) if False else (lambda c: (c.post('/login', data={'usuario': 'adriano', 'password': 'prueba-segura-123'}), c)[1])(A.app.test_client())))
nueva = entrar(); chk("con la nueva sí", adentro(nueva))
# máximo 30 días
with nueva.session_transaction() as s: s["inicio"] = int(time.time()) - 31 * 86400
chk("a los 30 días pide la contraseña aunque se use", not adentro(nueva))
nueva = entrar()
with nueva.session_transaction() as s: s["inicio"] = int(time.time()) - 29 * 86400
chk("a los 29 días sigue adentro", adentro(nueva))
# sesiones viejas (de antes de este cambio) y falsas
vieja = A.app.test_client()
with vieja.session_transaction() as s: s["logged_in"] = True; s["_permanent"] = True
chk("sesión de antes del cambio (sin versión) pide entrar de nuevo", not adentro(vieja))
inv = A.app.test_client()
with inv.session_transaction() as s: s.update({"logged_in": True, "ver": 0, "huella": "x", "inicio": int(time.time())})
chk("huella inventada no sirve", not adentro(inv))
chk("botón sin sesión no hace nada", A.app.test_client().post("/sesiones/cerrar-todas").status_code == 302)
chk("ajustes muestra el botón", "Cerrar sesión en todos los dispositivos" in nueva.get("/ajustes").get_data(as_text=True))
chk("API del asistente también cierra", inv.post("/asistente/chat", json={"mensaje": "hola"}).status_code in (401, 302))
print("FALLAS", F)
