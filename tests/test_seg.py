# ### CAMBIO AQUÍ ### PRUEBA AUTOMÁTICA — ¡BORRA LA BASE QUE USA!
# Solo corre con PRUEBAS_OK=1 y una base local (PRUEBAS_DATABASE_URL en localhost). Nunca la de Render o Neon.
import os as _os, sys as _sys
from urllib.parse import urlsplit as _us
_U = _os.environ.get("PRUEBAS_DATABASE_URL", "")
if not _U or (_us(_U).hostname or "") not in ("", "localhost", "127.0.0.1") or _os.environ.get("PRUEBAS_OK") != "1":
    _sys.exit("Estas pruebas BORRAN la base: solo corren con PRUEBAS_OK=1 y PRUEBAS_DATABASE_URL apuntando a una base local.")
import os, sys, json, io, zipfile, warnings
from datetime import date, timedelta
warnings.filterwarnings("ignore"); sys.path.insert(0, sys.argv[1])
os.environ.update(DATABASE_URL=_U, GROQ_API_KEY="x",
                  SECRET_KEY="clave-de-prueba-larga-123", ADMIN_USER="adriano", ADMIN_PASS="prueba-segura-123",
                  TAREAS_TOKEN="secreto123-largo-de-prueba", RENDER="true")
import psycopg2
c0 = psycopg2.connect(os.environ["DATABASE_URL"]); c0.autocommit = True
c0.cursor().execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"); c0.close()
import app as A, database as db, ia, privacidad as pv, competencia_auto as ca, competencia_ia as ci
A.app.config["PROPAGATE_EXCEPTIONS"] = True
fallas = 0
def chk(n, c, x=""):
    global fallas
    if not c: fallas += 1
    print(("OK " if c else "XX ") + n, "" if c else x)

# ---------- privacidad (unidad)
al = pv.armar_alias([("María José Gómez", 7), ("Juan Pérez", 9), ("Juan Rossi", 11), ("Ana Li", 12)])
t, u = pv.ocultar("¿Cuándo vino maria jose gomez? ¿Y Pérez? ¿Y Juan? ¿Y Ana?", al)
chk("nombre completo sin acentos", "Huésped #7" in t and "gomez" not in t.lower(), t)
chk("apellido único", "Huésped #9" in t and "Pérez" not in t, t)
chk("nombre ambiguo (Juan x2) no se adivina", "Juan" in t, t)
chk("nombre corto (Ana) no se toca", "Ana" in t, t)
chk("mostrar devuelve nombre real", pv.mostrar("Huésped #7 y huésped #9", al) == "María José Gómez y Juan Pérez")
chk("alias desconocido queda igual", pv.mostrar("Huésped #99", al) == "Huésped #99")
chk("palabra común no se toca", pv.ocultar("Mañana gané mucho", al)[0] == "Mañana gané mucho")

# ---------- datos
pid = db.execute("INSERT INTO propiedades (nombre,barrio,tipo,ambientes,capacidad,moneda) VALUES "
                 "('Depto Soho','Palermo','depto',2,4,'USD') RETURNING id")
rid = db.execute("INSERT INTO reservas (propiedad_id,codigo_confirmacion,huesped_nombre,fecha_inicio,fecha_fin,noches,"
                 "ingreso_neto,moneda) VALUES (%s,'HMX1','María José Gómez','2026-09-01','2026-09-05',4,520,'USD') RETURNING id", (pid,))
db.execute("INSERT INTO reservas (propiedad_id,codigo_confirmacion,huesped_nombre,fecha_inicio,fecha_fin,noches,"
           "ingreso_neto,moneda) VALUES (%s,'HMX2','Tomás Ferreyra','2026-09-10','2026-09-12',2,260,'USD')", (pid,))

# ---------- login: bloqueo
c = A.app.test_client()
for i in range(5):
    r = c.post("/login", data={"usuario": "adriano", "password": "mal"})
r = c.post("/login", data={"usuario": "adriano", "password": "prueba-segura-123"})
chk("6º intento bloqueado aunque la clave sea buena", r.status_code == 429 and "Demasiados" in r.get_data(as_text=True), r.status_code)
db.execute("DELETE FROM login_intentos")
r = c.post("/login", data={"usuario": "adriano", "password": "prueba-segura-123"})
ck = r.headers.get("Set-Cookie", "")
chk("login correcto", r.status_code == 302 and "/login" not in r.headers["Location"], r.status_code)
chk("cookie HttpOnly + Secure + SameSite=Lax + vence", all(x in ck for x in ("HttpOnly", "Secure", "SameSite=Lax", "Expires")), ck)
chk("usuario mal = rechazado", A.app.test_client().post("/login", data={"usuario": "x", "password": "prueba-segura-123"}).status_code == 200)
db.execute("DELETE FROM login_intentos")
# 4 fallos + 1 bueno → no bloquea y reinicia contador
c2 = A.app.test_client()
for i in range(4): c2.post("/login", data={"usuario": "adriano", "password": "mal"})
chk("4 fallos no bloquean", c2.post("/login", data={"usuario": "adriano", "password": "prueba-segura-123"}).status_code == 302)
chk("login correcto borra fallos", db.query_one("SELECT COUNT(*) n FROM login_intentos")["n"] == 0)

# ---------- chat: el nombre no llega a la IA
CAP = []
class R:
    def __init__(s, t): s.choices = [type('C', (), {'message': type('M', (), {'content': t})()})()]; s.usage = None
def fake(mensajes, modelo, max_tokens, temperature=0.3, **k):
    CAP.append(mensajes)
    return R(f"Huésped #{rid} se quedó 4 noches del 1 al 5 de septiembre.")
ia.completar = fake
r = c.post("/asistente/chat", json={"mensaje": "¿Cuándo vino María José Gómez y cuánto pagó?"})
todo = json.dumps(CAP[-1], ensure_ascii=False)
chk("ningún nombre real viaja a la IA", "Gómez" not in todo and "María" not in todo and "Ferreyra" not in todo, todo[:300])
chk("la IA recibe el alias y sus reservas", f"Huésped #{rid}" in todo and "RESERVAS DE LOS HUÉSPEDES QUE SE MENCIONAN" in todo
    and "2026-09-01 → 2026-09-05" in todo.split("QUE SE MENCIONAN")[1][:400], todo[-1500:])
resp = r.get_json()["respuesta"]
chk("Adriano ve el nombre real", resp.startswith("María José Gómez se quedó"), resp)
r = c.post("/asistente/chat", json={"mensaje": "¿y cuántas noches fueron?"})
todo2 = json.dumps(CAP[-1], ensure_ascii=False)
chk("historial (2º mensaje) también sin nombres", "Gómez" not in todo2 and len(CAP[-1]) >= 4, todo2[:200])
hist = A._cargar_historial()
chk("historial guardado con nombre real (local)", any("María José Gómez" in m["content"] for m in hist))

# ---------- reseña
def fake2(mensajes, modelo, max_tokens, temperature=0.3, **k):
    CAP.append(mensajes); return R("¡Gracias Huésped #0 por tu visita!")
ia.completar = fake2
c.post("/resenas/nueva", data={"propiedad_id": pid, "huesped": "Laura Benítez", "puntaje": 5,
                                "texto": "Laura Benítez aquí: excelente lugar, volvería"})
todo = json.dumps(CAP[-1], ensure_ascii=False)
chk("reseña: nombre no viaja", "Benítez" not in todo and "Huésped #0" in todo, todo[:300])
res = db.query_one("SELECT respuesta FROM resenas ORDER BY id DESC LIMIT 1")["respuesta"]
chk("reseña: respuesta con nombre real", res == "¡Gracias Laura Benítez por tu visita!", res)

# ---------- consulta de huésped
db.execute("UPDATE propiedades SET info_huespedes='Check-in 14 h' WHERE id=%s", (pid,))
def fake3(mensajes, modelo, max_tokens, temperature=0.3, **k):
    CAP.append(mensajes); return R("Hola Huésped #%s, el check-in es a las 14 h." % rid)
ia.completar = fake3
c.post("/asistente", data={"propiedad_id": pid, "mensaje": "Hola, soy María José Gómez, ¿a qué hora es el check-in?"})
todo = json.dumps(CAP[-1], ensure_ascii=False)
chk("consulta: nombre no viaja", "Gómez" not in todo, todo[:300])
q = db.query_one("SELECT respuesta FROM consultas_huespedes ORDER BY id DESC LIMIT 1")["respuesta"]
chk("consulta: respuesta con nombre real", "María José Gómez" in q, q)

# ---------- token de la tarea por encabezado
ca.correr_en_segundo_plano = lambda: None
chk("token por encabezado X-Token", c.get("/tareas/competencia", headers={"X-Token": "secreto123-largo-de-prueba"}).status_code == 200)
chk("token por URL sigue andando", c.get("/tareas/competencia?token=secreto123-largo-de-prueba").status_code == 200)
chk("token malo = 403", c.get("/tareas/competencia", headers={"X-Token": "otro"}).status_code == 403)

# ---------- competencia acumulada
hoy = date.today()
def res_(fecha, comps):
    return {"ok": True, "fecha": fecha, "fuente": "Tavily", "resumen": "r", "comparables": comps}
def comp(link, precio):
    return {"plataforma": "Booking", "titulo": "t", "zona": "Palermo", "ambientes": None, "capacidad": None,
            "precio_noche": precio, "moneda": "USD", "rating": None, "link": link, "nota": ""}
prop = db.query_one("SELECT * FROM propiedades WHERE id=%s", (pid,))
ca.guardar_resultado(prop, res_((hoy - timedelta(days=40)).isoformat(), [comp("https://viejo", 90)]), 1400)
ca.guardar_resultado(prop, res_((hoy - timedelta(days=2)).isoformat(), [comp("https://a", 100), comp("https://b", 120)]), 1400)
ca.guardar_resultado(prop, res_(hoy.isoformat(), [comp("https://b", 125), comp("https://c", 140)]), 1400)
ia_rows = db.query("SELECT link, precio_noche FROM competencia WHERE propiedad_id=%s AND origen='ia' ORDER BY link", (pid,))
chk("se acumulan días y se reemplaza el repetido", [(r["link"], r["precio_noche"]) for r in ia_rows] ==
    [("https://a", 100), ("https://b", 125), ("https://c", 140)], ia_rows)
chk("lo de más de 30 días se borra", not any(r["link"] == "https://viejo" for r in ia_rows))
c.post(f"/competencia?pid={pid}", data={"barrio": "Palermo", "tipo": "depto", "precio_noche": "110", "moneda": "USD",
                                        "plataforma": "Airbnb", "titulo": "Loft amigo", "link": ""})
man = db.query_one("SELECT * FROM competencia WHERE origen='manual'")
chk("carga manual queda asociada a la propiedad", man and man["propiedad_id"] == pid and man["titulo"] == "Loft amigo", man)
ca.guardar_resultado(prop, res_(hoy.isoformat(), [comp("https://d", 150)]), 1400)
chk("la carga manual no se borra en la corrida", db.query_one("SELECT COUNT(*) n FROM competencia WHERE origen='manual'")["n"] == 1)
h = db.query_one("SELECT cantidad, mediana FROM competencia_historial WHERE propiedad_id=%s AND fecha=%s", (pid, hoy.isoformat()))
chk("historial usa todo lo acumulado (4 IA + 1 manual)", h["cantidad"] == 5 and h["mediana"] == 125, h)
html = c.get(f"/competencia?pid={pid}").get_data(as_text=True)
chk("página: referencia de zona con conteo", "Precio de referencia de la zona" in html and "4 de la IA" in html and "1 cargados por vos" in html, "")
chk("página: badge Tuyo", "Tuyo" in html)
html = c.post("/precios", data={"propiedad_id": pid, "fecha": hoy.isoformat()}).get_data(as_text=True)
chk("precios usa la referencia acumulada (5)", "5 comparables" in html, html[html.find("Fuente"):html.find("Fuente") + 120])
chk("consultas usan los 2 dominios buenos", ci._consultas_tavily(prop) == ["departamento por noche Palermo Buenos Aires",
                                                                         "Palermo Buenos Aires apartment price per night"])
chk("sin MercadoLibre", not any("mercadolibre" in d for d in ci.DOMINIOS))

# ---------- informes: texto de la IA escapado
iid = db.execute("INSERT INTO informes (titulo, contenido, fecha_desde, fecha_hasta) VALUES "
                 "('x', '<script>alert(1)</script>\nlinea 2', '2026-01-01', '2026-01-31') RETURNING id")
html = c.get(f"/informes/{iid}").get_data(as_text=True)
chk("informe escapado", "<script>alert(1)" not in html and "&lt;script&gt;" in html)

# ---------- copia de seguridad
r = c.get("/respaldo/descargar")
z = zipfile.ZipFile(io.BytesIO(r.data))
nombres = z.namelist()
chk("zip con todas las tablas", {"propiedades.csv", "reservas.csv", "resenas.csv", "competencia.csv", "config.csv"} <= set(nombres), nombres)
chk("zip sin login_intentos", "login_intentos.csv" not in nombres)
chk("reservas con datos y acentos", "María José Gómez" in z.read("reservas.csv").decode("utf-8-sig"))
chk("respaldo pide login", A.app.test_client().get("/respaldo/descargar").status_code == 302)
chk("botón en Informes", "Descargar copia" in c.get("/informes").get_data(as_text=True))
chk("dashboard sigue andando", c.get("/").status_code == 200)

print("\nFALLAS:", fallas)
