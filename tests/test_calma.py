# ### CAMBIO AQUÍ ### PRUEBA AUTOMÁTICA — ¡BORRA LA BASE QUE USA!
# Solo corre con PRUEBAS_OK=1 y una base local (PRUEBAS_DATABASE_URL en localhost). Nunca la de Render o Neon.
import os as _os, sys as _sys
from urllib.parse import urlsplit as _us
_U = _os.environ.get("PRUEBAS_DATABASE_URL", "")
if not _U or (_us(_U).hostname or "") not in ("", "localhost", "127.0.0.1") or _os.environ.get("PRUEBAS_OK") != "1":
    _sys.exit("Estas pruebas BORRAN la base: solo corren con PRUEBAS_OK=1 y PRUEBAS_DATABASE_URL apuntando a una base local.")
import os, sys, re, warnings
from datetime import date, timedelta
warnings.filterwarnings("ignore"); sys.path.insert(0, sys.argv[1])
os.environ.update(DATABASE_URL=_U, GROQ_API_KEY="x", SECRET_KEY="clave-de-prueba-larga-123", ADMIN_USER="adriano", ADMIN_PASS="prueba-segura-123")
import psycopg2
c0 = psycopg2.connect(os.environ["DATABASE_URL"]); c0.autocommit = True
c0.cursor().execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"); c0.close()
import app as A, database as db
F = 0
def chk(n, ok, x=""):
    global F; F += not ok; print(("OK " if ok else "XX ") + n, "" if ok else x)
hoy = date.today(); D = lambda n: (hoy + timedelta(days=n)).isoformat()
c = A.app.test_client(); c.post("/login", data={"usuario": "adriano", "password": "prueba-segura-123"})
h = c.get("/hoy").get_data(as_text=True)
chk("sin propiedades: invita a empezar", "Subir el archivo de Airbnb" in h)
P = db.execute("INSERT INTO propiedades (nombre,barrio,precio_base,estado,moneda,ciudad,estadia_minima,costo_expensas,recambio_limpieza) VALUES ('Soho','Palermo',50000,'activa','ARS','BA',2,200000,15000) RETURNING id")
for cod, fi, ff in (("A1", D(-40), D(-37)), ("A2", D(-30), D(-27)), ("A3", D(-20), D(-17)), ("A4", D(4), D(9))):
    db.execute("""INSERT INTO reservas (propiedad_id,codigo_confirmacion,huesped_nombre,fecha_inicio,fecha_fin,noches,estado,ingreso_bruto,ingreso_neto,moneda,fecha_reserva,anticipacion_dias)
                  VALUES (%s,%s,'Ana Paz',%s,%s,3,'completada',150000,120000,'ARS',%s,20)""", (P, cod, fi, ff, D(-60)))
h = c.get("/hoy").get_data(as_text=True)
pasos = re.findall(r'class="card calma-paso" id="paso-(\d+)"', h)
chk("saludo y plan con cantidad de cambios", ("Buen día" in h or "Buenas" in h) and re.search(r"Hoy hay (un cambio|\d+ cambios) para hacer en Airbnb", h) and pasos, h[:300])
chk("cada paso: valor grande y botón Copiar", 'class="calma-monto"' in h and 'data-copiar="' in h)
chk("explicaciones plegadas", "Cómo hacerlo en Airbnb" in h and "<details class=\"mas\"><summary>Por qué" in h)
chk("panorama y feriados al final, plegados", 'id="panorama"' in h and f'id="techo-{P}"' in h and 'id="eventos"' in h)
m = re.search(r'name="clave" value="([^"]+)"><input type="hidden" name="estado" value="hecho">', h)
clave = m.group(1)
c.post("/acciones/estado", data={"clave": clave, "estado": "hecho", "silencioso": "1", "volver": "/hoy"})
h2 = c.get("/hoy").get_data(as_text=True)
chk("al hacer uno: avanza el progreso y ofrece Deshacer", ("Vas bien: 1 de" in h2 or "Terminaste todo" in h2) and "Deshacer" in h2)
chk("sin cartel verde de 'Marcado como hecho'", "Marcado como hecho" not in h2)
c.post("/acciones/deshacer", data={"clave": clave, "volver": "/hoy"})
h3 = c.get("/hoy").get_data(as_text=True)
chk("Deshacer: la tarea vuelve", f'value="{clave}"><input type="hidden" name="estado" value="hecho"' in h3 and "Vas bien" not in h3)
chk("Deshacer: no queda anotada como hecha", not db.query_one("SELECT 1 FROM acciones_estado WHERE clave=%s", (clave,)))
chk("Deshacer de otra clave no hace nada", c.post("/acciones/deshacer", data={"clave": "1:otra"}).status_code == 302)
# todo hecho
for k in re.findall(r'name="clave" value="([^"]+)"><input type="hidden" name="estado" value="hecho">', h3):
    c.post("/acciones/estado", data={"clave": k, "estado": "hecho", "silencioso": "1", "volver": "/hoy"})
h4 = c.get("/hoy").get_data(as_text=True)
chk("al terminar: 'Listo por hoy'", "Listo por hoy" in h4 and "Terminaste todo por hoy" in h4)
# precios
pr = c.get("/precios").get_data(as_text=True)
chk("precios: cifra grande con Copiar", 'class="precio-grande"' in pr and "Conviene cobrar ahora" in pr)
# lo que dice Qué hacer hoy coincide con Precios (mismas fechas, mismo precio)
import estrategia as E
db.execute("DELETE FROM acciones_estado")   # las de arriba quedaron hechas
a = E.analizar(db.query_one("SELECT * FROM propiedades WHERE id=%s", (P,)), db.query("SELECT * FROM reservas"), hoy, None, [], [])
libres = [x for x in E.acciones(a) if x["clave"].startswith(f"{P}:libre:")]
ok = True
for x in libres:
    _, _, d1, d2, precio = x["clave"].split(":")
    for k in range((date.fromisoformat(d2) - date.fromisoformat(d1)).days + 1):
        if E.precio_noche(date.fromisoformat(d1) + timedelta(days=k), a["cx"])[0] != int(precio): ok = False
chk("cada tarea de precio vale para todas sus noches (igual que en Precios)", libres and ok, [x["clave"] for x in libres])
chk("precios: barra mínimo / normal / techo", 'class="escala"' in pr and "Lo normal" in pr and "Mínimo" in pr)
chk("precios: próximas noches en fichas", 'class="precio-ficha"' in pr)
chk("precios: herramientas plegadas", f'id="pp-{P}"' in pr and "Más herramientas" in pr and "Ver costos del departamento" in pr)
print("FALLAS", F)
