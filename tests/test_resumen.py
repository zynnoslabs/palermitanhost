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
os.environ.update(DATABASE_URL=_U, GROQ_API_KEY="x", SECRET_KEY="clave-de-prueba-larga-123", ADMIN_USER="adriano",
                  ADMIN_PASS="prueba-segura-123", TAREAS_TOKEN="token-de-prueba-largo-123")
for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "MAIL_PARA", "APP_URL"): os.environ.pop(k, None)
import psycopg2
c0 = psycopg2.connect(os.environ["DATABASE_URL"]); c0.autocommit = True
c0.cursor().execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"); c0.close()
import app as A, database as db, resumen as rsm
F = 0
def chk(n, ok, x=""):
    global F; F += not ok; print(("OK " if ok else "XX ") + n, "" if ok else x)
hoy = date.today(); D = lambda n: (hoy + timedelta(days=n)).isoformat()
c = A.app.test_client(); c.post("/login", data={"usuario": "adriano", "password": "prueba-segura-123"})
P = db.execute("INSERT INTO propiedades (nombre,barrio,precio_base,estado,moneda,ciudad,estadia_minima) VALUES ('Soho','Palermo',50000,'activa','ARS','BA',2) RETURNING id")
for cod, fi, ff, nom in (("A1", D(-3), D(0), "Ana Perez"), ("A2", D(0), D(3), "Beto Diaz"), ("A3", D(6), D(9), "Caro Ruiz")):
    db.execute("""INSERT INTO reservas (propiedad_id,codigo_confirmacion,huesped_nombre,fecha_inicio,fecha_fin,noches,estado,ingreso_bruto,ingreso_neto,moneda)
                  VALUES (%s,%s,%s,%s,%s,3,'confirmada',150000,120000,'ARS')""", (P, cod, nom, fi, ff))
v = c.get("/resumen/vista").get_data(as_text=True)
chk("vista del mail: llegada, salida y limpieza", "Llega</strong> Beto" in v and "Sale</strong> Ana" in v and "Limpieza</strong> en Soho" in v)
chk("vista del mail: solo nombre de pila", "Diaz" not in v and "Perez" not in v)
chk("vista del mail: tareas de hoy", "Para hacer en Airbnb hoy" in v)
vm = c.get("/resumen/vista?mensual=1").get_data(as_text=True)
chk("vista con reporte del mes", "Cómo fue" in vm and "Noches vendidas" in vm)
aj = c.get("/ajustes").get_data(as_text=True)
chk("ajustes avisa que falta configurar el mail", "Falta configurar el mail" in aj and "Mandar uno de prueba" not in aj)
r = A.app.test_client().get("/tareas/resumen?token=" + "token-de-prueba-largo-123")
chk("sin mail configurado: la tarea avisa el error", r.status_code == 500 and "Falta configurar" in r.get_json()["error"])
chk("tarea sin token: 403", A.app.test_client().get("/tareas/resumen").status_code == 403 and A.app.test_client().get("/tareas/resumen?token=mal").status_code == 403)
# mail falso que captura lo enviado
enviados = []
class FakeSMTP:
    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def login(self, u, p):
        if p != "app-pass-ok": import smtplib; raise smtplib.SMTPAuthenticationError(535, b"no")
    def send_message(self, m): enviados.append(m)
    def starttls(self, **k): pass
rsm.smtplib.SMTP_SSL = FakeSMTP; rsm.smtplib.SMTP = FakeSMTP
os.environ.update(SMTP_HOST="smtp.gmail.com", SMTP_PORT="465", SMTP_USER="sistema@gmail.com", SMTP_PASS="app-pass-ok",
                  MAIL_PARA="adriano@ejemplo.com, pedro@ejemplo.com", APP_URL="https://palermitan.onrender.com")
r = A.app.test_client().get("/tareas/resumen", headers={"X-Token": "token-de-prueba-largo-123"})
chk("tarea manda el mail", r.status_code == 200 and len(enviados) == 1, r.get_data(as_text=True))
m = enviados[-1] if enviados else None
chk("mail a los dos destinatarios con asunto claro", m and m["To"] == "adriano@ejemplo.com, pedro@ejemplo.com" and "llegada" in m["Subject"])
chk("mail con botón para abrir el sistema", m and "palermitan.onrender.com/hoy" in m.get_body(("html",)).get_content())
r = A.app.test_client().get("/tareas/resumen?token=token-de-prueba-largo-123")
chk("no se manda dos veces el mismo día", len(enviados) == 1 and "ya se mandó" in r.get_json()["mensaje"])
c.post("/resumen/prueba"); chk("botón de prueba manda aunque ya haya salido", len(enviados) == 2 and enviados[-1]["Subject"].startswith("[Prueba]"))
os.environ["SMTP_PASS"] = "mala"
r = c.post("/resumen/prueba", follow_redirects=True).get_data(as_text=True)
chk("contraseña de mail mala: explica qué hacer", "contraseña de aplicación" in r)
rep = c.get("/reporte").get_data(as_text=True)
chk("página del reporte del mes", "Reporte de" in rep and "Sugerencias que seguiste" in rep)
chk("reporte con mes raro no rompe", c.get("/reporte?mes=xx").status_code == 200 and c.get("/reporte?mes=2999-01").status_code == 200)
print("FALLAS", F)
