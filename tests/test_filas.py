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
import app as A, database as db, alertas
F = 0
def chk(n, ok, x=""):
    global F; F += not ok; print(("OK " if ok else "XX ") + n, "" if ok else x)
c = A.app.test_client(); c.post("/login", data={"usuario": "adriano", "password": "prueba-segura-123"})
GAN = '''Date,Type,Confirmation Code,Booking date,Start date,Nights,Guest,Listing,Details,Reference code,Currency,Amount,Paid out,Service fee,Fast pay fee,Cleaning fee,Gross earnings,Occupancy taxes,Earnings year
08/06/2026,Reservation,HMPRUEBA01,07/10/2026,08/05/2026,3,Lucía Gómez,Depto Prueba,,,ARS,"156.600,00",,"-5.400,00",,"20.000,00","162.000,00",,2026
'''
RES = open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "datos", "Prueba_Precio_Airbnb.csv"), encoding="utf-8").read()
def subir(txt, tipo=None):
    data = {"csv_file": (io.BytesIO(txt.encode()), "x.csv")}
    if tipo: data["tipo"] = tipo
    return c.post("/importar", data=data, content_type="multipart/form-data")
h = c.get("/importar").text
chk("página con un renglón por archivo", all(x in h for x in ['id="subir-reservas"', 'id="subir-ganancias"', "Subir Reservas", "Subir Ganancias", "3. Calendario de Airbnb"]))
chk("cada renglón manda su tipo", 'name="tipo" value="reservas"' in h and 'name="tipo" value="ganancias"' in h)
r = subir(GAN, "reservas")
chk("Ganancias en el renglón de Reservas: frenado", r.status_code == 302 and "resaltar=subir-ganancias" in r.headers["Location"], r.headers.get("Location"))
h = c.get(r.headers["Location"]).text
chk("explica dónde va", "Ese archivo es de Ganancias, no de Reservas" in h)
chk("no importó nada", db.query_one("SELECT COUNT(*) n FROM reservas")["n"] == 0)
r = subir(RES, "ganancias")
chk("Reservas en el renglón de Ganancias: frenado", "resaltar=subir-reservas" in r.headers["Location"])
r = subir(RES, "reservas")
chk("Reservas en su renglón: sigue", "/importar/asignar" in r.headers["Location"], r.headers.get("Location"))
h = c.get(r.headers["Location"]).text; t = re.search(r'name="t" value="([^"]+)"', h).group(1)
r = c.post("/importar/asignar", data={"asignar": "1", "t": t, "prop_0": "nueva"}, follow_redirects=True)
chk("resultado avisa que faltan costos", "Falta completar a mano" in r.text and "costos mensuales" in r.text and "costos de recambio" in r.text)
chk("resultado ofrece el otro archivo y qué hacer hoy", "Subir el otro archivo" in r.text and "Ver qué hacer hoy" in r.text)
r = subir(GAN, "ganancias")
chk("Ganancias en su renglón: sigue", "/importar/asignar" in r.headers["Location"])
r = subir(GAN)
chk("sin tipo (compatibilidad): sigue", "/importar/asignar" in r.headers["Location"])
r = subir(GAN, "cualquiera")
chk("tipo raro: no rompe", "/importar/asignar" in r.headers["Location"])
h = c.get("/importar").text
chk("lista propiedad sin costos con link al campo", "Completá a mano" in h and "resaltar=costo_expensas" in h)
chk("calendario: 0 de 1 conectadas", "0 de 1 conectadas" in h)
db.execute("UPDATE propiedades SET costo_expensas=1, recambio_limpieza=1, barrio='Palermo', precio_base=1, ical_url='https://www.airbnb.com/calendar/ical/1.ics'")
h = c.get("/importar").text
chk("con todo completo: no avisa", "Completá a mano" not in h and "1 de 1 conectadas" in h)
links = [a["link"] for a in alertas.revisar() if "archivo" in a["titulo"].lower()]
chk("alertas de archivos apuntan a su renglón", all("subir-" in l for l in links), links)
print("FALLAS", F)
