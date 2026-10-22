# ### CAMBIO AQUÍ ### PRUEBA AUTOMÁTICA — ¡BORRA LA BASE QUE USA!
# Solo corre con PRUEBAS_OK=1 y una base local (PRUEBAS_DATABASE_URL en localhost). Nunca la de Render o Neon.
import os as _os, sys as _sys
from urllib.parse import urlsplit as _us
_U = _os.environ.get("PRUEBAS_DATABASE_URL", "")
if not _U or (_us(_U).hostname or "") not in ("", "localhost", "127.0.0.1") or _os.environ.get("PRUEBAS_OK") != "1":
    _sys.exit("Estas pruebas BORRAN la base: solo corren con PRUEBAS_OK=1 y PRUEBAS_DATABASE_URL apuntando a una base local.")
import os, sys, io, re, warnings, json
from datetime import date, timedelta
warnings.filterwarnings("ignore"); sys.path.insert(0, sys.argv[1])
os.environ.update(DATABASE_URL=_U, GROQ_API_KEY="x", SECRET_KEY="clave-de-prueba-larga-123", ADMIN_USER="adriano", ADMIN_PASS="prueba-segura-123")
import psycopg2
c0 = psycopg2.connect(os.environ["DATABASE_URL"]); c0.autocommit = True
c0.cursor().execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"); c0.close()
import app as A, database as db, alertas
F = 0
def chk(n, ok, x=""):
    global F
    F += not ok; print(("OK " if ok else "XX ") + n, "" if ok else x)
c = A.app.test_client(); c.post("/login", data={"usuario": "adriano", "password": "prueba-segura-123"})
hoy = date.today(); d = lambda n: (hoy + timedelta(days=n)).isoformat()
chk("sistema vacío: sin alertas", alertas.revisar() == [], alertas.revisar())
P1 = db.execute("INSERT INTO propiedades (nombre,barrio,precio_base,costo_expensas,estado,moneda) VALUES ('Soho','Palermo',30000,100000,'activa','ARS') RETURNING id")
P2 = db.execute("INSERT INTO propiedades (nombre,barrio,precio_base,estado,moneda) VALUES ('Loft','',0,'mantenimiento','USD') RETURNING id")
def res(cod, pid, fi, ff, est="confirmada", h="X", neto=100):
    db.execute("""INSERT INTO reservas (propiedad_id,codigo_confirmacion,huesped_nombre,fecha_inicio,fecha_fin,noches,estado,ingreso_neto,ingreso_bruto,moneda)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'ARS')""", (pid, cod, h, fi, ff, (date.fromisoformat(ff) - date.fromisoformat(fi)).days, est, neto, neto))
res("A", P1, d(-20), d(-15), "completada", "Ana"); res("B", P1, d(-17), d(-14), "completada", "Beto")   # se pisan
res("C", P1, d(2), d(4), "pendiente", "Caro")                                                            # pendiente que llega pronto
res("D", P2, d(5), d(8), "confirmada", "Dani")                                                           # propiedad en mantenimiento
res("E", P1, d(30), d(33), "cancelada", "Eli")
db.execute("INSERT INTO config (clave,valor) VALUES ('ultima_importacion_ganancias', %s)", (d(-40),))
db.execute("INSERT INTO resenas (propiedad_id,texto,pendiente,creada_en) VALUES (%s,'ok',1,NOW() - INTERVAL '10 days')", (P1,))
for i, pr in enumerate([50000, 52000, 48000, 55000, 51000]):
    db.execute("INSERT INTO competencia (propiedad_id,barrio,precio_noche,fecha,origen,moneda,link) VALUES (%s,'Palermo',%s,%s,'ia','ARS',%s)", (P1, pr, d(0), f"https://x/{i}"))
al = alertas.revisar()
tit = [a["titulo"] for a in al]; print("  ->", tit)
chk("superposición Ana/Beto", any(a["titulo"] == "Reservas superpuestas" and "Ana" in a["detalle"] and "Beto" in a["detalle"] for a in al))
chk("solicitud pendiente que llega en 2 días", "Solicitud sin confirmar" in tit)
chk("reserva en propiedad en mantenimiento", "Reserva en propiedad fuera de servicio" in tit)
chk("estadías sin cobro cargado", "Estadías terminadas sin el cobro cargado" in tit)
chk("archivo de Ganancias viejo (40 días)", any("Ganancias tiene 40 días" in t for t in tit))
chk("nunca se subió Reservas", "Nunca se subió el archivo de Reservas" in tit)
chk("faltan datos de Loft (barrio, precio, costos)", any(t == "Faltan datos de Loft" for t in tit))
chk("reseña sin responder", any("reseña(s) sin responder" in t for t in tit))
chk("falta tipo de cambio (hay USD)", "Falta el tipo de cambio" in tit)
chk("noches libres en Soho", any("Soho:" in t and "noches libres" in t for t in tit))
chk("precio 41% por debajo del mercado", any("por debajo del mercado" in t for t in tit))
chk("la cancelada no genera superposición ni alertas", not any("Eli" in a["detalle"] for a in al))
chk("ordenadas: primero las rojas", [a["nivel"] for a in al] == sorted([a["nivel"] for a in al], key=alertas.ORDEN.get))
rojo = alertas.revisar(hoy=date(hoy.year, hoy.month, 25) if hoy.day < 25 else hoy)
chk("mes en rojo (día 25, costos > ingresos)", any("costos superan" in a["titulo"] for a in rojo), [a["titulo"] for a in rojo])
h = c.get("/").text
chk("Dashboard: muestra alertas y 'ver más'", "Alertas (" in h and "más</summary>" in h)
mes = (hoy - timedelta(days=17)).strftime("%Y-%m")
r = c.get(f"/calendario?mes={mes}")
dias = json.loads(re.search(r"var DIAS = (\{.*?\});\n", r.text, re.S).group(1))
chk("calendario marca la noche superpuesta", dias[d(-16)]["choques"] == ["Soho"] if d(-16) in dias else True, dias.get(d(-16), {}).get("choques"))
chk("calendario: clase 'choque' en el día", "choque" in r.text)
db.execute("UPDATE propiedades SET estado='inactiva' WHERE id=%s", (P2,))
chk("filtro por propiedad", all("Loft" not in a["titulo"] for a in alertas.revisar(P1)))
print("FALLAS", F)
