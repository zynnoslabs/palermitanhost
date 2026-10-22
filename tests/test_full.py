# ### CAMBIO AQUÍ ### PRUEBA AUTOMÁTICA — ¡BORRA LA BASE QUE USA!
# Solo corre con PRUEBAS_OK=1 y una base local (PRUEBAS_DATABASE_URL en localhost). Nunca la de Render o Neon.
import os as _os, sys as _sys
from urllib.parse import urlsplit as _us
_U = _os.environ.get("PRUEBAS_DATABASE_URL", "")
if not _U or (_us(_U).hostname or "") not in ("", "localhost", "127.0.0.1") or _os.environ.get("PRUEBAS_OK") != "1":
    _sys.exit("Estas pruebas BORRAN la base: solo corren con PRUEBAS_OK=1 y PRUEBAS_DATABASE_URL apuntando a una base local.")
import os, sys, io, re, warnings, logging
warnings.filterwarnings("ignore")
sys.path.insert(0, sys.argv[1])
os.environ.update(DATABASE_URL=_U,
                  GROQ_API_KEY="x", SECRET_KEY="clave-de-prueba-larga-123", ADMIN_USER="adriano", ADMIN_PASS="prueba-segura-123")
import psycopg2
c0=psycopg2.connect(os.environ["DATABASE_URL"]); c0.autocommit=True
c0.cursor().execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"); c0.close()
import app as A, database as db
logging.getLogger('werkzeug').setLevel(logging.ERROR)
A.app.config["PROPAGATE_EXCEPTIONS"]=False
c = A.app.test_client()
def show(name, r, *must):
    ok = r.status_code < 400 and all(m in r.get_data(as_text=True) for m in must)
    print(f"{'OK ' if ok else 'XX '} {name}: {r.status_code}", "" if ok else [m for m in must if m not in r.get_data(as_text=True)])
show("login page", c.get("/login"))
# unauthenticated access checks
for u in ["/asistente/limpiar"]:
    print("sin login POST", u, c.post(u).status_code)
print("sin login chat", c.post("/asistente/chat", json={"mensaje":"hola"}).status_code)
print("sin login pdf", c.get("/informes/1/pdf").status_code)
c.post("/login", data={"usuario":"adriano","password":"prueba-segura-123"})
show("dashboard vacio", c.get("/"))
r=c.post("/propiedades/nueva", data={"nombre":"Departamento Palermo Soho","barrio":"Palermo","tipo":"depto","ambientes":"2","capacidad":"4","precio_base":"40000","costo_expensas":"50000","info_huespedes":"WiFi: casa123. Check-in 15hs."}, follow_redirects=True)
show("nueva propiedad", r, "Departamento Palermo Soho")
pid = db.query_one("SELECT id FROM propiedades")["id"]
# small CSV import
csvtxt = open(os.path.join(sys.argv[1],"reservas_ejemplo.csv"),encoding="utf-8").read()
r=c.post("/importar", data={"csv_file":(io.BytesIO(csvtxt.encode()),"r.csv")}, content_type="multipart/form-data", follow_redirects=True)
show("importar paso3", r, "Asignar anuncios")
r=c.post("/importar/asignar", data={"asignar":"1","prop_Departamento Palermo Soho":str(pid)}, follow_redirects=True)
print("   ", re.findall(r"\d+ reservas importadas[^<]*", r.get_data(as_text=True))[:1], "total en DB:", db.query_one("SELECT COUNT(*) n FROM reservas")["n"])
# big CSV (cookie limit)
head, *rows = csvtxt.strip().splitlines()
big = [head] + [re.sub(r"HM\d+", f"HB{i:09d}", rows[i % len(rows)]) for i in range(80)]
r=c.post("/importar", data={"csv_file":(io.BytesIO("\n".join(big).encode()),"b.csv")}, content_type="multipart/form-data", follow_redirects=True)
r=c.post("/importar/asignar", data={"asignar":"1","prop_Departamento Palermo Soho":str(pid)}, follow_redirects=True)
print("CSV 80 filas (%d bytes) -> en DB:" % len("\n".join(big)), db.query_one("SELECT COUNT(*) n FROM reservas")["n"], "| texto:", re.findall(r"\d+ reservas importadas[^<]*", r.get_data(as_text=True))[:1])
# montos
import importador as I
print("parsear_monto:", {t: I.parsear_monto(t) for t in ["45000","45.000","1,234.56","1.234,56","45000.00","-3150"]})
show("dashboard con datos", c.get("/?desde=2024-01-01&hasta=2024-12-31"))
show("propiedades", c.get("/propiedades"))
show("precios GET", c.get("/precios"))
show("precios POST", c.post("/precios", data={"propiedad_id":pid,"fecha_desde":"2026-11-01","fecha_hasta":"2026-11-05"}, follow_redirects=True))
show("asistente GET", c.get("/asistente"))
show("asistente POST", c.post("/asistente", data={"propiedad_id":pid,"mensaje":"cual es el wifi?"}, follow_redirects=True))
show("informes", c.get("/informes"))
# business chat: check context builds
import asistente_route as AR
conn=db.get_db()
try:
    p=AR.build_context(conn); print("OK  contexto chat negocio construido, len", len(p))
except Exception as e:
    print("XX  contexto chat negocio falla:", type(e).__name__, str(e).splitlines()[0]); conn.rollback()
finally: db._release(conn)
r=c.post("/asistente/chat", json={"mensaje":"hola"}); print("chat negocio:", r.status_code, r.get_json())
# informe + export
db.execute("INSERT INTO informes (titulo,contenido) VALUES ('t','## Resumen\nTodo bien')")
iid=db.query_one("SELECT id FROM informes")["id"]
for k in range(12):
    r=c.get(f"/informes/{iid}/pdf")
    if r.status_code!=200: print(f"XX  PDF intento {k+1}: {r.status_code}"); break
else: print("OK  12 PDFs seguidos")
r=c.get("/propiedades"); print("despues de exportar, /propiedades:", r.status_code)
# --- extra checks after fixes
r=c.get(f"/informes/{iid}"); print("ver informe:", r.status_code, "⬇ PDF" in r.get_data(as_text=True))
show("dashboard con informe", c.get("/"))
show("asistente con historial", c.get("/asistente"))
r=c.get(f"/informes/{iid}/excel"); print("excel:", r.status_code, r.headers.get("Content-Type","")[:40])
r=c.post("/importar", data={"csv_file":(io.BytesIO("\n".join(big).encode()),"b.csv")}, content_type="multipart/form-data")
ck=[h for h in r.headers.getlist("Set-Cookie") if h.startswith("session=")]
print("tamaño cookie tras subir CSV grande:", len(ck[0]) if ck else 0, "bytes (límite navegador 4096)")
import competencia_ia
db.execute("INSERT INTO competencia (propiedad_id,barrio,tipo,precio_noche,fecha,origen) VALUES (%s,'Palermo','depto',50000,'2026-10-07','ia')",(pid,))
conn=db.get_db()
try: p=AR.build_context(conn); print("contexto mercado:", [l for l in p.splitlines() if "anuncios similares" in l])
finally: db._release(conn)
s=met = __import__("metricas").calcular_metricas([{"noches":20,"ingreso_bruto":1000,"ingreso_neto":900}],"2026-01-01","2026-01-10",0,2)
print("ocupación 20 noches/10 días/2 unidades:", s["tasa_ocupacion"])
print("sin login chat ahora:", A.app.test_client().post("/asistente/chat", json={"mensaje":"x"}).status_code,
      "| sin login pdf:", A.app.test_client().get(f"/informes/{iid}/pdf").status_code)
