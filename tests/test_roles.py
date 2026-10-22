# ### CAMBIO AQUÍ ### PRUEBA AUTOMÁTICA — ¡BORRA LA BASE QUE USA!
# Solo corre con PRUEBAS_OK=1 y una base local (PRUEBAS_DATABASE_URL en localhost). Nunca la de Render o Neon.
import os as _os, sys as _sys
from urllib.parse import urlsplit as _us
_U = _os.environ.get("PRUEBAS_DATABASE_URL", "")
if not _U or (_us(_U).hostname or "") not in ("", "localhost", "127.0.0.1") or _os.environ.get("PRUEBAS_OK") != "1":
    _sys.exit("Estas pruebas BORRAN la base: solo corren con PRUEBAS_OK=1 y PRUEBAS_DATABASE_URL apuntando a una base local.")
import os, sys, time, warnings
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
def entrar(u, p):
    c = A.app.test_client(); r = c.post("/login", data={"usuario": u, "password": p}); return c, r
admin, _ = entrar("adriano", "prueba-segura-123")
# puesta a punto sin propiedades / con propiedad incompleta
P = db.execute("INSERT INTO propiedades (nombre,barrio,precio_base,estado,moneda,ciudad,direccion,recambio_limpieza) VALUES ('Soho','Palermo',50000,'activa','ARS','BA','Gorriti 4500',15000) RETURNING id")
h = admin.get("/hoy").get_data(as_text=True)
chk("puesta a punto aparece con lo que falta", "Puesta a punto" in h and "Estadía mínima" in h and "Calendario de Airbnb" in h)
# reservas: sale hoy y entra otro hoy; sale en 3 días sin llegada
for cod, fi, ff, nom in (("A1", D(-3), D(0), "Ana Perez"), ("A2", D(0), D(3), "Beto Diaz"), ("A3", D(5), D(8), "Caro Ruiz")):
    db.execute("""INSERT INTO reservas (propiedad_id,codigo_confirmacion,huesped_nombre,fecha_inicio,fecha_fin,noches,estado,ingreso_bruto,ingreso_neto,moneda)
                  VALUES (%s,%s,%s,%s,%s,3,'confirmada',150000,120000,'ARS')""", (P, cod, nom, fi, ff))
db.execute("INSERT INTO config (clave,valor) VALUES ('ultima_importacion_reservas',%s) ON CONFLICT (clave) DO UPDATE SET valor=EXCLUDED.valor", (D(-10),))
h = admin.get("/hoy").get_data(as_text=True)
chk("aviso de datos viejos (10 días, sin calendario)", "Las reservas tienen 10 días" in h)
l = admin.get("/limpiezas").get_data(as_text=True)
chk("limpiezas: 3 salidas", l.count('class="card limp') == 3, l.count('class="card limp'))
chk("limpiezas: urgente si entra otro el mismo día", "Entra otro huésped ese día" in l)
chk("limpiezas: dueño ve costo y botón de WhatsApp", "Costo del recambio" in l and "wa.me" in l)
chk("limpiezas: sin nombres de huéspedes", not any(x in l for x in ("Ana", "Beto", "Caro")))
# crear usuarios
r = admin.post("/usuarios/nuevo", data={"nombre": "Marta", "usuario": "marta", "clave": "limpia-1234", "rol": "limpieza"}, follow_redirects=True)
chk("crear usuario de limpieza", "Usuario creado" in r.get_data(as_text=True))
r = admin.post("/usuarios/nuevo", data={"nombre": "X", "usuario": "marta", "clave": "otra-clave-123", "rol": "limpieza"}, follow_redirects=True)
chk("no deja repetir usuario", "ya existe" in r.get_data(as_text=True))
r = admin.post("/usuarios/nuevo", data={"nombre": "X", "usuario": "corta", "clave": "123", "rol": "limpieza"}, follow_redirects=True)
chk("pide contraseña de 10+", "al menos 10" in r.get_data(as_text=True))
admin.post("/usuarios/nuevo", data={"nombre": "Juli", "usuario": "juli", "clave": "coanfi-12345", "rol": "coanfitrion"})
chk("la contraseña se guarda cifrada", "limpia-1234" not in str(db.query("SELECT clave_hash FROM usuarios")))
# limpieza
m, r = entrar("marta", "limpia-1234")
chk("limpieza entra directo a Limpiezas", r.headers["Location"].endswith("/limpiezas"))
lm = m.get("/limpiezas").get_data(as_text=True)
chk("limpieza no ve costos ni WhatsApp", "Costo del recambio" not in lm and "wa.me" not in lm and "ARS" not in lm)
for u in ("/hoy", "/", "/precios", "/calendario", "/propiedades", "/asistente", "/informes"):
    rr = m.get(u)
    if not (rr.status_code == 302 and rr.headers["Location"].endswith("/limpiezas")): chk(f"limpieza bloqueada en {u}", False, rr.status_code)
chk("limpieza no entra a ninguna otra página", True)
chk("limpieza no puede usar el asistente", m.post("/asistente/chat", json={"mensaje": "cuanto gané"}).status_code == 403)
chk("limpieza no puede crear usuarios", m.post("/usuarios/nuevo", data={"nombre": "h", "usuario": "hack", "clave": "1234567890", "rol": "coanfitrion"}).status_code == 403
    and not db.query_one("SELECT 1 FROM usuarios WHERE usuario='hack'"))
clave = f"{P}:{hoy.isoformat()}"
m.post("/limpiezas/estado", data={"clave": clave, "estado": "hecha"})
chk("limpieza marca lista y queda quién", "Lista · Marta" in admin.get("/limpiezas").get_data(as_text=True))
chk("clave rara no se guarda", m.post("/limpiezas/estado", data={"clave": "x'; drop", "estado": "hecha"}).status_code == 302 and db.query_one("SELECT COUNT(*) n FROM limpiezas_estado")["n"] == 1)
aj = m.get("/ajustes").get_data(as_text=True)
chk("limpieza ve Ajustes de lectura pero no usuarios ni cerrar todas", "Tamaño de letra" in aj and "Otros usuarios" not in aj and "todos los dispositivos" not in aj)
# co-anfitrión
j, r = entrar("juli", "coanfi-12345")
chk("co-anfitrión entra a Qué hacer hoy", r.headers["Location"].endswith("/hoy") and j.get("/hoy").status_code == 200)
chk("co-anfitrión ve precios y números", j.get("/precios").status_code == 200 and j.get("/").status_code == 200)
chk("co-anfitrión no puede borrar propiedades", j.post(f"/propiedades/{P}/eliminar").status_code == 403 and db.query_one("SELECT 1 FROM propiedades WHERE id=%s", (P,)))
chk("co-anfitrión no baja el respaldo", j.get("/respaldo/descargar").status_code == 302)
chk("co-anfitrión no cierra sesiones de todos", j.post("/sesiones/cerrar-todas").status_code == 403)
chk("co-anfitrión no maneja usuarios", "Otros usuarios" not in j.get("/ajustes").get_data(as_text=True))
# desactivar / cambiar clave
uid = db.query_one("SELECT id FROM usuarios WHERE usuario='marta'")["id"]
admin.post(f"/usuarios/{uid}/clave", data={"clave": "nueva-clave-999"})
chk("cambiar la clave cierra su sesión", m.get("/limpiezas").status_code == 302)
chk("entra con la nueva", entrar("marta", "nueva-clave-999")[1].headers["Location"].endswith("/limpiezas"))
m2, _ = entrar("marta", "nueva-clave-999")
admin.post(f"/usuarios/{uid}/estado", data={"activo": "0"})
chk("desactivado: se le cierra la sesión", m2.get("/limpiezas").status_code == 302)
chk("desactivado: no puede entrar", entrar("marta", "nueva-clave-999")[1].status_code == 200)
chk("el dueño sigue adentro", admin.get("/hoy").status_code == 200)
# PWA
chk("manifest y service worker se sirven", A.app.test_client().get("/static/manifest.webmanifest").status_code == 200
    and A.app.test_client().get("/sw.js").headers["Content-Type"].startswith("application/javascript"))
chk("login tiene el manifest", "manifest.webmanifest" in A.app.test_client().get("/login").get_data(as_text=True))
print("FALLAS", F)
