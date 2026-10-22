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
import psycopg2
c0 = psycopg2.connect(os.environ["DATABASE_URL"]); c0.autocommit = True
c0.cursor().execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"); c0.close()
import app as A, database as db, estrategia as E
A.app.config["PROPAGATE_EXCEPTIONS"] = True
F = 0
def chk(n, ok, x=""):
    global F; F += not ok; print(("OK " if ok else "XX ") + n, "" if ok else x)
hoy = date.today(); D = lambda n: hoy + timedelta(days=n)
c = A.app.test_client(); c.post("/login", data={"usuario": "adriano", "password": "prueba-segura-123"})
P = db.execute("INSERT INTO propiedades (nombre,barrio,precio_base,estado,moneda,ciudad,estadia_minima,recambio_limpieza) VALUES ('Soho','Palermo',50000,'activa','ARS','Buenos Aires',5,20000) RETURNING id")
k=[0]
def res(fi, n, ant=20, precio=50000, nombre="Ana Gomez"):
    k[0]+=1
    db.execute("""INSERT INTO reservas (propiedad_id,codigo_confirmacion,huesped_nombre,fecha_inicio,fecha_fin,noches,estado,ingreso_bruto,ingreso_neto,moneda,fecha_reserva,anticipacion_dias)
                  VALUES (%s,%s,%s,%s,%s,%s,'confirmada',%s,%s,'ARS',%s,%s)""", (P,f"R{k[0]}",nombre,D(fi).isoformat(),D(fi+n).isoformat(),n,precio*n,precio*n*.85,D(fi-ant).isoformat(),ant))
res(0, 2)            # ocupado hoy y mañana
res(5, 6, nombre="Bruno Diaz")   # libre 2..4 (3 noches, hueco < mínima 5) → ocupado 5..10
res(13, 3)           # libre 11..12 (2 noches)
reservas = db.query("SELECT * FROM reservas")
prop = db.query_one("SELECT * FROM propiedades WHERE id=%s", (P,))
a = E.analizar(prop, reservas, hoy, None, [], [])
acc = E.acciones(a)
lib = [x for x in acc if x["clave"].startswith(f"{P}:libre:")]
chk("hay tarea de noches libres", bool(lib), [x["titulo"] for x in acc])
for x in lib:
    imp = x["impacto"]; ini = date.fromisoformat(x["clave"].split(":")[2]); fin = date.fromisoformat(x["clave"].split(":")[3])
    p = int(x["clave"].split(":")[4]); n = (fin-ini).days+1
    esperado = p*n - 20000 if "estadía mínima" in x["hacer"] else p*n   # hueco abierto: entra 1 recambio (sin limpieza cobrada)
    chk(f"impacto {x['titulo'][:40]} = {imp['monto']}", imp and abs(imp["monto"] - esperado) <= 1, (imp, esperado, x["hacer"]))
    chk("el Por qué explica el impacto", any(o.startswith("Impacto: ") for o in x["origen"]))
chk("cfg sin impacto", all(not x["impacto"] for x in acc if x["cfg"]))
h = c.get("/hoy").text
chk("hoy muestra impacto", "accion-imp" in h and "en juego hoy" in h, h[:200])
# timeline
t = c.get("/calendario?vista=linea").text
chk("línea de tiempo abre", 'class="tl"' in t and "Soho" in t)
chk("muestra huésped y precio", "Bruno" in t and "Libre" in t and "$ " in t)
chk("hueco corto marcado", "libre corto" in t and "nadie puede reservar" in t)
chk("nombre completo no se muestra", "Bruno Diaz" not in t)
m = c.get("/calendario").text
chk("recuerda la vista elegida", 'class="tl"' in m)
m = c.get("/calendario?vista=mes").text
chk("vuelve a vista mes", "cal-grid" in m and 'class="tl"' not in m)
chk("desde raro no rompe", c.get("/calendario?vista=linea&desde=xx").status_code == 200 and c.get("/calendario?vista=linea&desde=1999-01-01").status_code == 200)
t2 = c.get(f"/calendario?vista=linea&desde={D(500).isoformat()}").text
chk("desde lejano se limita", 'class="tl"' in t2)
chk("filtro propiedad", c.get(f"/calendario?vista=linea&propiedad_id={P}").status_code == 200)
# sin propiedades ni reservas
chk("ajustes abre", "Tamaño de letra" in c.get("/ajustes").text)
chk("menú tiene Ajustes", "Ajustes" in c.get("/hoy").text)
print("FALLAS", F)
