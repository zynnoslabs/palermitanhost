# ### CAMBIO AQUÍ ### PRUEBA AUTOMÁTICA — ¡BORRA LA BASE QUE USA!
# Solo corre con PRUEBAS_OK=1 y una base local (PRUEBAS_DATABASE_URL en localhost). Nunca la de Render o Neon.
import os as _os, sys as _sys
from urllib.parse import urlsplit as _us
_U = _os.environ.get("PRUEBAS_DATABASE_URL", "")
if not _U or (_us(_U).hostname or "") not in ("", "localhost", "127.0.0.1") or _os.environ.get("PRUEBAS_OK") != "1":
    _sys.exit("Estas pruebas BORRAN la base: solo corren con PRUEBAS_OK=1 y PRUEBAS_DATABASE_URL apuntando a una base local.")
import os, sys, io, re, warnings
from datetime import date, timedelta
warnings.filterwarnings("ignore"); sys.path.insert(0, sys.argv[1])
os.environ.update(DATABASE_URL=_U, GROQ_API_KEY="x", SECRET_KEY="clave-de-prueba-larga-123", ADMIN_USER="adriano", ADMIN_PASS="prueba-segura-123")
import psycopg2
c0 = psycopg2.connect(os.environ["DATABASE_URL"]); c0.autocommit = True
c0.cursor().execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"); c0.close()
import app as A, database as db, estrategia as E, disposicion_pago as dp
A.app.config["PROPAGATE_EXCEPTIONS"] = True
F = 0
def chk(n, ok, x=""):
    global F; F += not ok; print(("OK " if ok else "XX ") + n, "" if ok else x)
hoy = date.today()
c = A.app.test_client(); c.post("/login", data={"usuario": "adriano", "password": "prueba-segura-123"})
txt = open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "datos", "Prueba_Precio_Airbnb.csv"), encoding="utf-8").read()
r1 = c.post("/importar", data={"csv_file": (io.BytesIO(txt.encode()), "x.csv"), "tipo": "reservas"}, content_type="multipart/form-data")
h = c.get(r1.headers["Location"]).text; t = re.search(r'name="t" value="([^"]+)"', h).group(1)
c.post("/importar/asignar", data={"asignar": "1", "t": t, "prop_0": "nueva"})
P = db.query_one("SELECT * FROM propiedades"); pid = P["id"]
h = c.get("/hoy").text
chk("una sola sección en el menú", "Estrategia</a>" not in h and h.count("Qué hacer hoy") >= 2)
chk("las 3 tarjetas", all(x in h for x in [f'id="techo-{pid}"', f'id="descuentos-{pid}"', f'id="disponibilidad-{pid}"', "Techo de precio", "Descuentos", "Disponibilidad"]))
chk("detalle plegado adentro", f'id="detalle-{pid}"' in h and f'id="precios-{pid}"' in h and f'id="estadia-{pid}"' in h and f'id="pruebas-{pid}"' not in h)
chk("feriados y eventos al final", 'id="eventos"' in h and "Agregar evento" in h)
a = E.analizar(P, db.query("SELECT * FROM reservas"), hoy, None, [])
s = E.situacion(a)
print("   techo:", s["techo"]["numero"], "|", s["techo"]["texto"])
print("   descuentos:", s["descuentos"]["numero"], "|", s["descuentos"]["texto"])
print("   disponibilidad:", s["disponibilidad"]["numero"], "|", s["disponibilidad"]["texto"])
t = a["dp"]["techo"]
chk("techo = 90% de lo pagado (verificable)", s["techo"]["numero"].replace("$", "").replace(".", "").strip() == str(t["p90"]), (s["techo"]["numero"], t))
chk("techo explica de dónde sale", any("90% de esas reservas" in x for x in s["techo"]["origen"]))
f0 = a["dp"]["ritmo"]["filas"][0]
if f0["tipo"] == "subir":
    chk("si vende rápido: sin descuento y el mismo precio en tarjeta y tarea", s["descuentos"]["numero"] == "0%" and "poné $ 55.000" in s["techo"]["texto"] and any("poné $ 55.000" in x["titulo"] for x in E.acciones(a)))
libres = 30 - len({hoy + timedelta(days=k) for k in range(30)} & a["ocup"])
chk("disponibilidad cuenta bien", s["disponibilidad"]["numero"] == f"{libres} de 30", s["disponibilidad"]["numero"])
chk("sin recambio: lo pide", "Cargá el costo de recambio" in s["disponibilidad"]["texto"])
# links viejos y nuevos
r = c.get(f"/estrategia?propiedad_id={pid}&resaltar=precios")
chk("link viejo de estrategia → hoy, resaltando precios", r.status_code == 302 and f"resaltar=precios-{pid}" in r.headers["Location"])
r = c.get("/estrategia"); chk("estrategia sin propiedad → hoy", r.headers["Location"].endswith("/hoy"))
acc = E.acciones(a)
chk("tareas apuntan a hoy", all("estrategia" not in (x["link"] or "") for x in acc), [x["link"] for x in acc])
r = c.post("/pruebas/nueva", data={"propiedad_id": pid, "fecha": (hoy - timedelta(days=3)).isoformat(), "tipo": "promo", "porcentaje": "10"})
chk("anotar prueba vuelve a Pruebas", r.headers["Location"].endswith("/pruebas"))
# sin datos: tarjetas no inventan
db.execute("INSERT INTO propiedades (nombre,barrio,precio_base,estado,moneda) VALUES ('Nueva','Palermo',0,'activa','ARS')")
Pn = db.query_one("SELECT * FROM propiedades WHERE nombre='Nueva'")
sn = E.situacion(E.analizar(Pn, db.query("SELECT * FROM reservas"), hoy, None, []))
chk("propiedad sin datos: techo '—' y explica", sn["techo"]["numero"] == "—" and "Faltan reservas" in sn["techo"]["texto"])
chk("propiedad sin datos: descuento '—'", sn["descuentos"]["numero"] == "—")
chk("hoy abre con 2 propiedades", c.get("/hoy").status_code == 200)
print("FALLAS", F)
