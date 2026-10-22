# ### CAMBIO AQUÍ ### PRUEBA AUTOMÁTICA — ¡BORRA LA BASE QUE USA!
# Solo corre con PRUEBAS_OK=1 y una base local (PRUEBAS_DATABASE_URL en localhost). Nunca la de Render o Neon.
import os as _os, sys as _sys
from urllib.parse import urlsplit as _us
_U = _os.environ.get("PRUEBAS_DATABASE_URL", "")
if not _U or (_us(_U).hostname or "") not in ("", "localhost", "127.0.0.1") or _os.environ.get("PRUEBAS_OK") != "1":
    _sys.exit("Estas pruebas BORRAN la base: solo corren con PRUEBAS_OK=1 y PRUEBAS_DATABASE_URL apuntando a una base local.")
import os, sys, warnings, random
from datetime import date, timedelta
warnings.filterwarnings("ignore"); sys.path.insert(0, sys.argv[1])
os.environ.update(DATABASE_URL=_U, GROQ_API_KEY="x", SECRET_KEY="clave-de-prueba-larga-123", ADMIN_USER="adriano", ADMIN_PASS="prueba-segura-123")
import psycopg2
c0 = psycopg2.connect(os.environ["DATABASE_URL"]); c0.autocommit = True
c0.cursor().execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"); c0.close()
import app as A, database as db, alertas, disposicion_pago as dp
F = 0
def chk(n, ok, x=""):
    global F; F += not ok; print(("OK " if ok else "XX ") + n, "" if ok else x)
hoy = date.today(); D = lambda n: hoy + timedelta(days=n)
c = A.app.test_client(); c.post("/login", data={"usuario": "adriano", "password": "prueba-segura-123"})
P = db.execute("INSERT INTO propiedades (nombre,barrio,precio_base,estado,moneda,costo_expensas) VALUES ('Soho','Palermo',50000,'activa','ARS',100000) RETURNING id")
prop = db.query_one("SELECT * FROM propiedades WHERE id=%s", (P,))
k = [0]
def res(fi, n, ant, precio=50000, est="completada", limp=10000, mon="ARS", fr=True):
    k[0] += 1; fi_d = fi; fr_d = fi_d - timedelta(days=ant)
    db.execute("""INSERT INTO reservas (propiedad_id,codigo_confirmacion,huesped_nombre,fecha_inicio,fecha_fin,noches,estado,
                  ingreso_bruto,ingreso_neto,limpieza,moneda,fecha_reserva,anticipacion_dias) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
               (P, f"R{k[0]}", f"H{k[0]}", fi_d.isoformat(), (fi_d + timedelta(days=n)).isoformat(), n, est,
                precio * n + limp, precio * n * .85, limp, mon, fr_d.isoformat() if fr else None, ant))
# sin reservas
chk("sin reservas → None", dp.analizar(prop, []) is None)
html = c.get(f"/precios?propiedad_id={P}").get_data(as_text=True)
chk("página sin reservas abre", c.get(f"/precios?propiedad_id={P}").status_code == 200 and "Precios por noche" in html)
# pocas reservas
res(D(-100), 3, 20); res(D(-80), 3, 20)
a = dp.analizar(prop, db.query("SELECT * FROM reservas"))
chk("pocas: no suficiente, sin ritmo", a and not a["suficiente"] and a["ritmo"] is None)
chk("pocas: página avisa", "Se necesitan al menos 5" in c.get(f"/precios?propiedad_id={P}").get_data(as_text=True))
# historia: un año, ~50% ocupación, anticipación 20 días
d = -360
while d < -10:
    res(D(d), 4, 20 + random.choice([-5, 0, 5])); d += 8
# una reservada mucho antes (90 días) y una a último momento (1 día)
res(D(-9), 2, 90, precio=60000); res(D(-6), 2, 1, precio=40000)
# basura: cancelada, sin noches, reserva después de la llegada, sin fecha de reserva
res(D(5), 3, 10, est="cancelada"); res(D(-200), 0, 5); res(D(-300), 2, -3); res(D(-310), 2, 15, fr=False)
# futuro: próximas 2 semanas muy vendidas (10 de 14), 15-30 normal, 30-60 vacío
res(D(0), 5, 25); res(D(6), 5, 30)
reservas = db.query("SELECT * FROM reservas")
a = dp.analizar(prop, reservas, mediana_mercado=55000)
chk("suficiente", a["suficiente"], a["con_fecha"])
chk("mediana anticipación ~20", 15 <= a["mediana_ant"] <= 25, a["mediana_ant"])
r = a["ritmo"]; chk("hay ritmo", r is not None)
f0 = r["filas"][0]; print("  ", [(f["nombre"], f["real"], f["esperado"], f["tipo"]) for f in r["filas"]], "ocup normal", r["ocup_normal"])
chk("ocupación normal ~50%", 40 <= r["ocup_normal"] <= 55, r["ocup_normal"])
chk("próximas 2 semanas → subir", f0["tipo"] == "subir" and f0["real"] == 71, f0)
chk("1-2 meses vacío no dice bajar fuerte", r["filas"][2]["tipo"] in ("neutra", "bajar"))
fl = {x["huesped"]: x for x in a["filas"]}
alta = next(x for x in a["filas"] if x["ant"] == 90); ult = next(x for x in a["filas"] if x["ant"] == 1)
chk("90 días antes → subir", alta["tipo"] == "subir" and alta["precio"] == 60000, alta)
chk("1 día antes → límite", ult["tipo"] == "limite")
chk("precio sin limpieza", alta["precio"] == 60000)
chk("vs mercado", alta["vs_mercado"] == 9, alta["vs_mercado"])
chk("techo", a["techo"]["maximo"] == 60000 and a["techo"]["mediana"] == 50000, a["techo"])
chk("cancelada no cuenta en la lista", all(x["huesped"] != "H%d" % 0 for x in a["filas"]))
# alerta
tits = [x["titulo"] for x in alertas.revisar()]
chk("alerta de vender más rápido", any("más rápido de lo normal" in t for t in tits), tits)
al = next(x for x in alertas.revisar() if "más rápido" in x["titulo"])
chk("alerta lleva a precios y resalta ritmo", al["link"] == f"precios?propiedad_id={P}&resaltar=ritmo")
html = c.get(f"/precios?propiedad_id={P}").get_data(as_text=True)
chk("página muestra todo", all(s in html for s in [f'id="ritmo-{P}"', "Techo probado", "Cómo venís vendiendo", "Costos", "Cada recambio"]))
chk("página sin errores de plantilla", "Traceback" not in html)
# moneda: propiedad en USD sin tipo de cambio
db.execute("UPDATE propiedades SET moneda='USD' WHERE id=%s", (P,))
prop2 = db.query_one("SELECT * FROM propiedades WHERE id=%s", (P,))
a2 = dp.analizar(prop2, reservas, tc=None)
chk("USD sin TC: no rompe, avisa y sigue el ritmo", a2["sin_tc"] > 0 and a2["techo"] is None and a2["ritmo"])
r = c.get(f"/precios?propiedad_id={P}"); chk("página USD sin TC abre", r.status_code == 200)
a3 = dp.analizar(prop2, reservas, tc=1000)
chk("USD con TC convierte", a3["techo"]["mediana"] == 50, a3["techo"])
db.execute("UPDATE propiedades SET moneda='ARS', estado='inactiva' WHERE id=%s", (P,))
chk("propiedad inactiva: sin alerta", not any("más rápido" in x["titulo"] for x in alertas.revisar()))
# fin de semana / todo vendido
db.execute("UPDATE propiedades SET estado='activa' WHERE id=%s", (P,))
res(D(5), 1, 20)  # completa 0-13? (0-5,6-11 ocupadas; 5 libre → ahora ocupada; 11,12,13 libres)
print("FALLAS", F)
