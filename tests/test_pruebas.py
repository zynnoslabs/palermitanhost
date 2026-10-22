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
import app as A, database as db, pruebas as PR, estrategia as E, ical
A.app.config["PROPAGATE_EXCEPTIONS"] = True
F = 0
def chk(n, ok, x=""):
    global F; F += not ok; print(("OK " if ok else "XX ") + n, "" if ok else x)
hoy = date.today(); D = lambda n: hoy + timedelta(days=n)
c = A.app.test_client(); c.post("/login", data={"usuario": "adriano", "password": "prueba-segura-123"})
h = c.get("/pruebas").text
chk("página vacía abre", "Lo que aprendió el sistema" in h and "Todavía nada" in h and "Anotar una prueba" in h)
chk("menú tiene Pruebas", ">⚗</span> Pruebas" in h)
P = db.execute("INSERT INTO propiedades (nombre,barrio,precio_base,estado,moneda,ciudad) VALUES ('Soho','Palermo',50000,'activa','ARS','Buenos Aires') RETURNING id")
k = [0]
def res(fi, n, ant, precio=50000, est="completada"):
    k[0] += 1
    db.execute("""INSERT INTO reservas (propiedad_id,codigo_confirmacion,huesped_nombre,fecha_inicio,fecha_fin,noches,estado,ingreso_bruto,ingreso_neto,moneda,fecha_reserva,anticipacion_dias)
                  VALUES (%s,%s,'H',%s,%s,%s,%s,%s,%s,'ARS',%s,%s)""", (P, f"R{k[0]}", D(fi).isoformat(), D(fi + n).isoformat(), n, est, precio * n, precio * n * .85, D(fi - ant).isoformat(), ant))
for i in range(8):
    res(-300 + i * 20, 3, 20)          # historia: se reserva 20 días antes
def post(**d):
    return c.post("/pruebas/nueva", data={"propiedad_id": P, "fecha": hoy.isoformat(), **d}, follow_redirects=True).text
n0 = lambda: db.query_one("SELECT COUNT(*) n FROM pruebas_descuento")["n"]
chk("precio sin fechas: rechazado", "para qué fechas" in post(tipo="precio", valor="60000") and n0() == 0)
chk("fecha futura: rechazada", "no puede ser futura" in post(tipo="descuento", valor="10", fecha=D(2).isoformat()) and n0() == 0)
chk("% 95: rechazado", "entre 0 y 90" in post(tipo="descuento", valor="95") and n0() == 0)
chk("mínima 0: rechazada", "entre 1 y 365" in post(tipo="minima", valor="0") and n0() == 0)
chk("hasta antes que desde: rechazado", "no puede ser anterior" in post(tipo="precio", valor="60000", desde=D(10).isoformat(), hasta=D(5).isoformat()) and n0() == 0)
chk("tipo raro: rechazado", "Elegí qué cambiaste" in post(tipo="hackeo", valor="1") and n0() == 0)
# A: subió y se vendió rápido (reservado 28 días antes, lo normal 20)
db.execute("INSERT INTO pruebas_descuento (propiedad_id,fecha,tipo,desde,hasta,valor,sugerido) VALUES (%s,%s,'precio',%s,%s,60000,50000)", (P, D(-60).isoformat(), D(-30).isoformat(), D(-28).isoformat()))
res(-30, 3, 28, 60000)
# B: subió 10% y se vendió normal
db.execute("INSERT INTO pruebas_descuento (propiedad_id,fecha,tipo,desde,hasta,valor,sugerido) VALUES (%s,%s,'precio',%s,%s,55000,50000)", (P, D(-50).isoformat(), D(-20).isoformat(), D(-18).isoformat()))
res(-20, 3, 20, 55000)
# C: subió 40% y no se vendió (fechas pasadas)
db.execute("INSERT INTO pruebas_descuento (propiedad_id,fecha,tipo,desde,hasta,valor,sugerido) VALUES (%s,%s,'precio',%s,%s,70000,50000)", (P, D(-40).isoformat(), D(-10).isoformat(), D(-8).isoformat()))
# D: precio a futuro sin vender todavía → esperando
db.execute("INSERT INTO pruebas_descuento (propiedad_id,fecha,tipo,desde,hasta,valor,sugerido) VALUES (%s,%s,'precio',%s,%s,58000,50000)", (P, hoy.isoformat(), D(30).isoformat(), D(32).isoformat()))
# E: descuento hace 30 días: antes 0 reservas hechas, después 1 → trajo más
db.execute("INSERT INTO pruebas_descuento (propiedad_id,fecha,tipo,valor) VALUES (%s,%s,'descuento',10)", (P, D(-80).isoformat()))
res(-50, 2, 25)   # reservada el día -75 (después del descuento)
# F: sacó la promoción hace 5 días → esperando
db.execute("INSERT INTO pruebas_descuento (propiedad_id,fecha,tipo,valor) VALUES (%s,%s,'saque_promocion',15)", (P, D(-5).isoformat()))
ev = {(x["tipo"], x["valor"]): x for x in PR.evaluar_todas(hoy)}
chk("A: 🟢 se vendió rápido", ev[("precio", 60000)]["codigo"] == "rapido" and ev[("precio", 60000)]["color"] == "🟢", ev[("precio", 60000)])
chk("B: 🟢 funcionó", ev[("precio", 55000)]["codigo"] == "ok", ev[("precio", 55000)])
chk("C: 🔴 no se vendió, era mucho", ev[("precio", 70000)]["codigo"] == "no" and "era mucho" in ev[("precio", 70000)]["texto"], ev[("precio", 70000)])
chk("D: ⚪ esperando", ev[("precio", 58000)]["color"] == "⚪" and "faltan" in ev[("precio", 58000)]["texto"], ev[("precio", 58000)])
chk("E: 🟢 descuento trajo más reservas", ev[("descuento", 10)]["codigo"] == "ok", ev[("descuento", 10)])
chk("F: ⚪ esperando 14 días", ev[("saque_promocion", 15)]["color"] == "⚪")
chk("explica cada resultado", all(x["detalle"] for x in ev.values()))
ap = PR.aprendizaje(P, list(ev.values()))
print("   aprendizaje:", ap)
chk("aprende: la gente paga ~10% más (3 pruebas, mediana de 1.26/1.10/0.97)", ap and ap["n"] == 3 and abs(ap["factor"] - 1.10) < 0.01 and ap["activo"], ap)
a = E.analizar(db.query_one("SELECT * FROM propiedades WHERE id=%s", (P,)), db.query("SELECT * FROM reservas"), hoy, None, [])
p1, m1 = E.precio_noche(D(40), a["cx"]); p0, _ = E.precio_noche(D(40), a["cx"], aprender=False)
chk("el precio sugerido usa lo aprendido y lo dice", p1 > p0 and any("aprendido de tus pruebas" in m for m in m1), (p0, p1, m1))
h = c.get("/pruebas").text
chk("página: aprendido + resultados + esperando", "La gente paga" in h and "Resultados (" in h and "Esperando resultado (" in h and "🟢" in h and "🔴" in h)
chk("lecciones de descuento", "Poner descuento trajo más reservas en 1 de 1 prueba" in h)
c.post(f"/pruebas/aprendizaje/{P}", data={})
a2 = E.analizar(db.query_one("SELECT * FROM propiedades WHERE id=%s", (P,)), db.query("SELECT * FROM reservas"), hoy, None, [])
p2, m2 = E.precio_noche(D(40), a2["cx"])
chk("deshacer: ya no se aplica", p2 == p0 and not any("aprendido" in m for m in m2) and "Volver a usar" in c.get("/pruebas").text)
c.post(f"/pruebas/aprendizaje/{P}", data={"activar": "1"})
chk("volver a usar", "No usar" in c.get("/pruebas").text)
# pocas pruebas: se aplica la mitad
db.execute("DELETE FROM pruebas_descuento WHERE valor IN (55000, 70000)")
ap1 = PR.aprendizaje(P, PR.evaluar_todas(hoy))
chk("1 prueba: ajuste a medias", ap1 and ap1["n"] == 1 and abs(ap1["factor"] - (1 + (1.25 - 1) / 2)) < 0.01 and "a medias" in ap1["texto"], ap1)
# manual con superposición
txt = post(tipo="precio", valor="62000", desde=D(31).isoformat(), hasta=D(33).isoformat())
chk("se mezcla con otra prueba: avisa pero guarda", "los resultados se pueden mezclar" in txt and n0() == 5, n0())
row = db.query_one("SELECT * FROM pruebas_descuento WHERE valor=62000")
chk("guarda lo que sugería el sistema", row["sugerido"] and row["sugerido"] > 0 and row["origen"] == "manual", row)
# ✓ Hecho desde Qué hacer hoy
hh = c.get("/hoy").text
m = re.search(r'name="clave" value="([^"]+)"><input type="hidden" name="estado" value="hecho">\s*<input type="hidden" name="p_pid" value="(\d+)"><input type="hidden" name="p_tipo" value="(\w+)">\s*<input type="hidden" name="p_desde" value="([^"]*)"><input type="hidden" name="p_hasta" value="([^"]*)">\s*<input type="hidden" name="p_valor" value="([^"]*)"><input type="hidden" name="p_sugerido" value="([^"]*)">', hh)
chk("tareas con precio traen la prueba", m is not None)
if m:
    datos = dict(clave=m.group(1), estado="hecho", p_pid=m.group(2), p_tipo=m.group(3), p_desde=m.group(4), p_hasta=m.group(5), p_valor=m.group(6), p_sugerido=m.group(7), volver="/hoy")
    antes = n0()
    r = c.post("/acciones/estado", data=datos, follow_redirects=True)
    chk("✓ Hecho la anota en Pruebas", n0() == antes + 1 and "Quedó anotado en Pruebas" in r.text)
    c.post("/acciones/estado", data=datos)
    chk("no se duplica", n0() == antes + 1)
    chk("queda marcada como 'desde Qué hacer hoy'", "desde Qué hacer hoy" in c.get("/pruebas").text)
r = c.post("/acciones/estado", data={"clave": "x:otra", "estado": "hecho", "p_tipo": "precio", "p_pid": "999", "p_valor": "1"}, follow_redirects=True)
chk("datos falsos en Hecho: no anota ni rompe", r.status_code == 200 and not db.query_one("SELECT id FROM pruebas_descuento WHERE propiedad_id=999"))
# borrar
pid_borrar = db.query_one("SELECT id FROM pruebas_descuento ORDER BY id DESC LIMIT 1")["id"]
c.post(f"/pruebas/{pid_borrar}/eliminar")
chk("borrar prueba", not db.query_one("SELECT id FROM pruebas_descuento WHERE id=%s", (pid_borrar,)))
chk("Qué hacer hoy ya no tiene pruebas", "Pruebas que hiciste" not in c.get("/hoy").text)
r = c.get("/estrategia?propiedad_id=1&resaltar=pruebas"); chk("link viejo a pruebas → página nueva", "/pruebas" in r.headers["Location"])
# calendario desde Importar
r = c.post(f"/calendario-airbnb/{P}/link", data={"ical_url": "https://evil.com/calendar/ical/1.ics"}, follow_redirects=True)
chk("Importar: link malo rechazado", "tiene que ser el de Airbnb" in r.text and not db.query_one("SELECT ical_url FROM propiedades WHERE id=%s", (P,))["ical_url"])
ICS = "BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART;VALUE=DATE:%s\nDTEND;VALUE=DATE:%s\nSUMMARY:Reserved\nEND:VEVENT\nEND:VCALENDAR" % (D(50).strftime("%Y%m%d"), D(53).strftime("%Y%m%d"))
ical._descargar = lambda u: ICS
r = c.post(f"/calendario-airbnb/{P}/link", data={"ical_url": "https://www.airbnb.com.ar/calendar/ical/9.ics?s=a"}, follow_redirects=True)
chk("Importar: link bueno se guarda y se lee", "conectado y leído" in r.text and db.query_one("SELECT COUNT(*) n FROM ical_bloqueos")["n"] == 1)
h = c.get("/importar").text
chk("Importar: muestra el link y 'leído'", "9.ics" in h and "✓ leído" in h and "1 de 1 conectadas" in h)
ical._descargar = lambda u: "<html>"
r = c.post(f"/calendario-airbnb/{P}/link", data={"ical_url": "https://www.airbnb.com.ar/calendar/ical/9.ics?s=a"}, follow_redirects=True)
chk("Importar: si Airbnb no responde bien, avisa", "no se pudo leer" in r.text)
r = c.post(f"/calendario-airbnb/{P}/link", data={"ical_url": ""}, follow_redirects=True)
chk("Importar: vaciar desconecta", "Se desconectó" in r.text and db.query_one("SELECT COUNT(*) n FROM ical_bloqueos")["n"] == 0)
# la IA conoce las pruebas
import asistente_route as AR, ia
env = {}
ia.completar = lambda m, *a, **k: env.setdefault("m", m) or "x"; ia.texto_respuesta = lambda r: "ok"
c.post("/asistente/chat", json={"mensaje": "¿qué aprendiste?"})
chk("la IA ve pruebas y aprendizaje", "Pruebas que hizo Adriano" in env["m"][0]["content"] and "Aprendido de las pruebas" in env["m"][0]["content"])
print("FALLAS", F)
