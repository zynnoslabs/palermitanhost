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
import app as A, database as db
F = 0
def chk(n, ok, x=""):
    global F
    F += not ok; print(("OK " if ok else "XX ") + n, "" if ok else x)
c = A.app.test_client(); c.post("/login", data={"usuario": "adriano", "password": "prueba-segura-123"})
def imp(txt):
    r1 = c.post("/importar", data={"csv_file": (io.BytesIO(txt.encode()), "x.csv")}, content_type="multipart/form-data")
    h = c.get(r1.headers["Location"]).text; t = re.search(r'name="t" value="([^"]+)"', h).group(1)
    sel = re.findall(r'<select name="prop_(\d+)">\s*<option value="">[^<]*</option>\s*<option value="nueva"( selected)?', h)
    data = {"asignar": "1", "t": t}
    for i, _ in sel:
        data[f"prop_{i}"] = re.search(rf'name="prop_{i}">.*?<option value="(\d+|nueva)" selected', h, re.S).group(1) if re.search(rf'name="prop_{i}">.*?<option value="(\d+|nueva)" selected', h, re.S) else "nueva"
    c.post("/importar/asignar", data=data)
hoy = date.today(); f = lambda d: (hoy + timedelta(days=d)).strftime("%m/%d/%Y")
cab = "Confirmation code,Status,Guest name,Start date,End date,# of nights,Booked,Listing,Earnings\n"
imp(cab + f'HMA,Confirmed,Ana Pérez,{f(0)},{f(3)},3,{f(-10)},Depto Soho,"$100,000.00"\n'
          f'HMB,Confirmed,Beto Gil,{f(1)},{f(4)},3,{f(-2)},Depto Soho,"$120,000.00"\n'
          f'HMC,Past guest,Caro Luna,{f(-3)},{f(0)},3,{f(-30)},Depto Soho,"$90,000.00"\n'
          f'HMD,Confirmed,Dani Paz,{f(10)},{f(12)},2,{f(-1)},Depto Soho,"$70,000.00"\n')
H = {e["codigo"]: e for e in db.query("SELECT * FROM reservas_historial")}
chk("historial: 'reservó' con la fecha real de Airbnb", H["HMA"]["tipo"] == "reservada" and H["HMA"]["fecha"] == (hoy - timedelta(days=10)).isoformat() and H["HMA"]["fecha_real"])
imp(cab + f'HMD,Canceled by guest,Dani Paz,{f(10)},{f(12)},2,{f(-1)},Depto Soho,"$70,000.00"\n'
          f'HMB,Confirmed,Beto Gil,{f(2)},{f(5)},3,{f(-2)},Depto Soho,"$130,000.00"\n')
tipos = sorted((e["codigo"], e["tipo"]) for e in db.query("SELECT * FROM reservas_historial WHERE NOT fecha_real"))
chk("detecta cancelación, cambio de fechas y de monto", ("HMD", "cancelada") in tipos and ("HMB", "fechas") in tipos and ("HMB", "monto") in tipos, tipos)
imp(cab + f'HMD,Canceled by guest,Dani Paz,{f(10)},{f(12)},2,{f(-1)},Depto Soho,"$70,000.00"\n')
chk("subir de nuevo no repite novedades", db.query_one("SELECT COUNT(*) n FROM reservas_historial WHERE codigo='HMD' AND tipo='cancelada'")["n"] == 1)
gan = ("Date,Type,Confirmation Code,Start date,Nights,Guest,Listing,Currency,Amount,Gross earnings\n"
       f"{f(-2)},Reservation,HMC,{f(-3)},3,Caro Luna,Depto Soho,ARS,85000,90000\n")
imp(gan); imp(gan)
cob = db.query("SELECT * FROM reservas_historial WHERE tipo='cobro'")
chk("cobro con su fecha real, una sola vez", len(cob) == 1 and cob[0]["fecha"] == (hoy - timedelta(days=2)).isoformat() and cob[0]["fecha_real"], cob)
h = c.get("/").text
t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))
chk("aviso: HOY llega Ana", re.search(r"HOY 🛬 Llega Ana Pérez a Depto Soho", t) is not None, t[:600])
chk("aviso: HOY se va Caro", "Se va Caro Luna" in t)
chk("aviso: canceló Dani", "CANCELÓ" in t and "Dani Paz" in t)
chk("aviso: cambio de Beto", "Beto Gil: cambió las fechas" in t)
chk("menú: número de movimientos de hoy (2)", re.search(r'nav-badge[^>]*>2<', h) is not None)
r = c.get("/calendario"); chk("calendario abre", r.status_code == 200)
dias = json.loads(re.search(r"var DIAS = (\{.*?\});\n", r.text, re.S).group(1))
k = hoy.isoformat()
chk("calendario hoy: llega Ana, se va Caro", [x["huesped"] for x in dias[k]["llegan"]] == ["Ana Pérez"] and [x["huesped"] for x in dias[k]["salen"]] == ["Caro Luna"], dias[k])
chk("calendario: cobro en su día", any("Cobro" in x["detalle"] for x in dias[(hoy - timedelta(days=2)).isoformat()]["cobros"]) if (hoy - timedelta(days=2)).month == hoy.month else True)
for q in ("?mes=2026-13", "?mes=abc", "?mes=2027-01&propiedad_id=1", "?dia=2026-10-11"):
    chk(f"calendario {q}", c.get("/calendario" + q).status_code == 200)
pid = db.query_one("SELECT id FROM propiedades")["id"]
h = c.get(f"/propiedades?ver={pid}").text
chk("propiedades: historial con fechas", "Historial (" in h and "detectado al subir el archivo" in h)
print("FALLAS", F)
