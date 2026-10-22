# ### CAMBIO AQUÍ ### PRUEBA AUTOMÁTICA — ¡BORRA LA BASE QUE USA!
# Solo corre con PRUEBAS_OK=1 y una base local (PRUEBAS_DATABASE_URL en localhost). Nunca la de Render o Neon.
import os as _os, sys as _sys
from urllib.parse import urlsplit as _us
_U = _os.environ.get("PRUEBAS_DATABASE_URL", "")
if not _U or (_us(_U).hostname or "") not in ("", "localhost", "127.0.0.1") or _os.environ.get("PRUEBAS_OK") != "1":
    _sys.exit("Estas pruebas BORRAN la base: solo corren con PRUEBAS_OK=1 y PRUEBAS_DATABASE_URL apuntando a una base local.")
import os, sys, io, re, warnings, time
from datetime import date, datetime, timezone, timedelta
warnings.filterwarnings("ignore"); sys.path.insert(0, sys.argv[1])
os.environ.update(DATABASE_URL=_U, GROQ_API_KEY="x",
                  SECRET_KEY="clave-de-prueba-larga-123", ADMIN_USER="adriano", ADMIN_PASS="prueba-segura-123", TAREAS_TOKEN="z"*20)
for k in ("SERPAPI_API_KEY", "TAVILY_API_KEY"):
    os.environ.pop(k, None)
import psycopg2
c0 = psycopg2.connect(os.environ["DATABASE_URL"]); c0.autocommit = True
c0.cursor().execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"); c0.close()
import app as A, database as db, monedas, competencia_ia
fallas = 0
def chk(n, c, x=""):
    global fallas
    if not c: fallas += 1
    print(("OK " if c else "XX ") + n, "" if c else x)

# ── HORA ──
hoy_ar = datetime.now(timezone(timedelta(hours=-3))).date()
chk("date.today() = día de Buenos Aires", date.today() == hoy_ar, (date.today(), hoy_ar))
r = db.query_one("SELECT CURRENT_DATE AS d, current_setting('TimeZone') AS tz")
chk("la base usa hora de Buenos Aires", r["tz"] == "America/Argentina/Buenos_Aires" and r["d"] == hoy_ar, r)

# ── FORMATOS ──
chk("dinero negativo", monedas.formatear(-253236, "ARS") == "-$ 253.236", monedas.formatear(-253236, "ARS"))
chk("dinero USD", monedas.formatear(1234.6, "USD") == "US$ 1.235")
f = A.app.jinja_env.filters
chk("num 70.8 → 70,8", f["num"](70.8) == "70,8")
chk("num 4.0 → 4", f["num"](4.0) == "4")
chk("num 4.71 (2) → 4,71", f["num"](4.712, 2) == "4,71")
chk("fecha → 05/10/2026", f["fecha"]("2026-10-05") == "05/10/2026" and f["fecha"](date(2026, 10, 5)) == "05/10/2026")
chk("fecha con hora", f["fecha"](datetime(2026, 10, 5, 21, 30), 16) == "05/10/2026 21:30")

c = A.app.test_client()
c.post("/login", data={"usuario": "adriano", "password": "prueba-segura-123"})

# ── SISTEMA VACÍO ──
chk("sin propiedades", db.query_one("SELECT COUNT(*) n FROM propiedades")["n"] == 0)
chk("sin reservas", db.query_one("SELECT COUNT(*) n FROM reservas")["n"] == 0)
chk("sin competencia", db.query_one("SELECT COUNT(*) n FROM competencia")["n"] == 0)
chk("sin tipo de cambio", monedas.get_tc() is None)
paginas = sorted({r.rule for r in A.app.url_map.iter_rules()
                  if "GET" in r.methods and "<" not in r.rule and not r.rule.startswith("/static")
                  and r.rule not in ("/logout", "/respaldo/descargar") and "tareas" not in r.rule and "moneda" not in r.rule})
for p in paginas:
    resp = c.get(p)
    h = resp.get_data(as_text=True)
    ok = resp.status_code in (200, 302) or (p == "/borrar-todo" and resp.status_code == 404)   # apagada sin la variable
    chk(f"vacío {p} → {resp.status_code}", ok and "Traceback" not in h)
    for palabra in ("Palermo", "Lucía", "Soho", "4.5★", "4,5★"):
        if palabra in h and 'placeholder="Ej: Palermo"' not in h:
            chk(f"  {p} sin dato inventado '{palabra}'", False, re.findall(r".{40}" + palabra + r".{20}", h)[:2])

# ── PROPIEDADES ──
c.post("/propiedades/nueva", data={"nombre": "Depto Soho", "barrio": "Palermo", "ciudad": "Buenos Aires", "tipo": "depto",
                                   "ambientes": 2, "capacidad": 3, "moneda": "USD"})
c.post("/propiedades/nueva", data={"nombre": "Studio VC", "barrio": "Villa Crespo", "ciudad": "", "tipo": "depto", "moneda": "ARS"})
c.post("/propiedades/nueva", data={"nombre": "Sin barrio", "barrio": "", "ciudad": "Córdoba", "tipo": "depto", "moneda": "ARS"})
props = {p["nombre"]: p for p in db.query("SELECT * FROM propiedades")}
chk("ciudad guardada", props["Depto Soho"]["ciudad"] == "Buenos Aires" and props["Studio VC"]["ciudad"] == "Buenos Aires")
chk("sin barrio no se crea la propiedad", "Sin barrio" not in props)
res = competencia_ia.buscar_comparables({"id": 0, "barrio": "", "ciudad": "Córdoba"}, con_resumen=False)
chk("sin barrio no busca 'Palermo'", not res["ok"] and "barrio" in (res["error"] or ""), res.get("error"))
q = competencia_ia._consultas_tavily({"barrio": "Nueva Córdoba", "ciudad": "Córdoba"})
chk("búsqueda usa la ciudad de la propiedad", all("Córdoba" in x and "Buenos Aires" not in x for x in q), q)
chk("prompt usa la ciudad", "Córdoba, Argentina" in competencia_ia._prompt({"barrio": "Centro", "ciudad": "Córdoba"}))
h = c.get(f"/propiedades/{props['Depto Soho']['id']}/editar").get_data(as_text=True)
chk("formulario muestra Ciudad", 'name="ciudad"' in h and "Buenos Aires" in h)
P1, P2 = props["Depto Soho"]["id"], props["Studio VC"]["id"]

def importar(csv_txt, asignacion, raw=None):
    datos = raw if raw is not None else csv_txt.encode("utf-8-sig")
    r1 = c.post("/importar", data={"csv_file": (io.BytesIO(datos), "x.csv")},
                content_type="multipart/form-data")
    if r1.status_code != 302 or "asignar" not in r1.headers.get("Location", ""):
        return None, r1.get_data(as_text=True) + str(r1.headers.get("Location"))
    h = c.get("/importar/asignar").get_data(as_text=True)
    anuncios = re.findall(r'<label>([^<]*)</label>\s*<select name="prop_(\d+)"', h)
    form = {"asignar": "1"}
    import html as _h
    for nombre, i in anuncios:
        nombre = _h.unescape(nombre)
        form[f"prop_{i}"] = str(asignacion.get(nombre, ""))
    r2 = c.post("/importar/asignar", data=form)
    if r2.status_code != 302:
        return None, r2.get_data(as_text=True)
    r3 = c.get(r2.headers["Location"])
    return r3.get_data(as_text=True), None

GAN_EN = """Date,Type,Confirmation Code,Booking date,Start date,Nights,Guest,Listing,Details,Reference code,Currency,Amount,Paid out,Service fee,Fast pay fee,Cleaning fee,Gross earnings,Occupancy taxes,Earnings year
10/07/2026,Payout,,,,,,,Transfer to Account ****1234 (USD),,USD,,"1,951.10",,,,,,
10/05/2026,Reservation,HMABC123,09/20/2026,10/05/2026,3,Lucía Pérez,Depto Soho,,,USD,US$ 251.10,,(8.90),,20.00,US$ 260.00,,2026
09/02/2026,Reservation,HMLONG1,08/01/2026,09/01/2026,40,John Smith,Depto Soho,,,USD,900.00,,-100.00,,0,"1,000.00",,2026
10/02/2026,Reservation,HMLONG1,08/01/2026,09/01/2026,40,John Smith,Depto Soho,,,USD,800.00,,-100.00,,0,900.00,,2026
10/13/2026,Reservation,HMCAN01,10/01/2026,10/13/2026,2,Ana Ruiz,Depto Soho,,,USD,50.00,,-5.00,,0,55.00,,2026
"""
h, err = importar(GAN_EN, {"Depto Soho": P1})
chk("import Ganancias (inglés) sin pedir columnas", err is None, (err or "")[:300])
R = {r["codigo_confirmacion"]: r for r in db.query("SELECT * FROM reservas")}
a = R.get("HMABC123", {})
chk("fecha mes/día: 10/05/2026 = 5 de octubre", str(a.get("fecha_inicio"))[:10] == "2026-10-05", a.get("fecha_inicio"))
chk("bruto = Gross earnings (260)", a.get("ingreso_bruto") == 260, a.get("ingreso_bruto"))
chk("neto = Amount (251,10 con 'US$')", abs((a.get("ingreso_neto") or 0) - 251.10) < .01, a.get("ingreso_neto"))
chk("comisión (8.90) negativa", abs((a.get("comision_airbnb") or 0) + 8.90) < .01, a.get("comision_airbnb"))
chk("limpieza 20", a.get("limpieza") == 20)
chk("anticipación 15 días", a.get("anticipacion_dias") == 15, a.get("anticipacion_dias"))
chk("moneda USD", a.get("moneda") == "USD")
L = R.get("HMLONG1", {})
chk("estadía larga partida: se suma (neto 1700, bruto 1900)", L.get("ingreso_neto") == 1700 and L.get("ingreso_bruto") == 1900,
    (L.get("ingreso_neto"), L.get("ingreso_bruto")))
chk("estadía larga: 40 noches", L.get("noches") == 40)
chk("fila Payout no es error", "filas con errores" not in (h or ""), re.findall(r"\d+ filas con errores", h or ""))
chk("3 reservas", len(R) == 3, list(R))
# reimportar el mismo archivo no duplica ni suma dos veces
importar(GAN_EN, {"Depto Soho": P1})
L = db.query_one("SELECT * FROM reservas WHERE codigo_confirmacion='HMLONG1'")
chk("reimportar no duplica montos", L["ingreso_neto"] == 1700 and db.query_one("SELECT COUNT(*) n FROM reservas")["n"] == 3)

RES_EN = """Confirmation code,Status,Guest name,Contact,# of adults,# of children,# of infants,Start date,End date,# of nights,Booked,Listing,Earnings
HMABC123,Past guest,Lucía Pérez,+54 11 5555-5555,2,0,0,10/05/2026,10/08/2026,3,09/20/2026,Depto Soho,US$251.10
HMFUT01,Confirmed,Pedro Gómez,+54 11 4444-4444,2,0,0,12/20/2026,12/27/2026,7,10/01/2026,Depto Soho,"US$1,400.00"
HMCAN01,Canceled by guest,Ana Ruiz,,1,0,0,10/13/2026,10/15/2026,2,10/01/2026,Depto Soho,US$0.00
"""
h, err = importar(RES_EN, {"Depto Soho": P1})
chk("import Reservas (inglés)", err is None, (err or "")[:300])
R = {r["codigo_confirmacion"]: r for r in db.query("SELECT * FROM reservas")}
a = R["HMABC123"]
chk("Reservas NO pisa el bruto real (sigue 260)", a["ingreso_bruto"] == 260, a["ingreso_bruto"])
chk("Reservas completa fecha de salida", str(a["fecha_fin"])[:10] == "2026-10-08", a["fecha_fin"])
chk("estado 'Past guest' → completada", a["estado"] == "completada", a["estado"])
fu = R.get("HMFUT01", {})
chk("reserva futura 20/12 entra como confirmada", str(fu.get("fecha_inicio"))[:10] == "2026-12-20" and fu.get("estado") == "confirmada",
    (fu.get("fecha_inicio"), fu.get("estado")))
chk("monto futura 1.400 (con coma de miles)", fu.get("ingreso_neto") == 1400, fu.get("ingreso_neto"))
chk("cancelada", R["HMCAN01"]["estado"] == "cancelada")
# Ganancias después de Reservas: no 'des-cancela'
importar(GAN_EN, {"Depto Soho": P1})
chk("Ganancias después no reactiva la cancelada", db.query_one("SELECT estado FROM reservas WHERE codigo_confirmacion='HMCAN01'")["estado"] == "cancelada")

GAN_ES = """Fecha,Tipo,Código de confirmación,Fecha de la reserva,Fecha de inicio,Noches,Huésped,Anuncio,Detalles,Código de referencia,Moneda,Importe,Pagado,Tarifa de servicio,Tarifa de pago rápido,Tarifa de limpieza,Ingresos brutos,Impuestos de ocupación,Año de ingresos
26/08/2026,Pago,,,,,,,Transferencia,,ARS,,"116.400,00",,,,,,
25/08/2026,Reserva,HMES001,01/08/2026,25/08/2026,2,Juan Gómez,Studio VC,,,ARS,"$ 116.400,00",,"-3.600,00",,"10.000,00","$ 120.000,00",,2026
"""
h, err = importar(GAN_ES, {"Studio VC": P2})
chk("import Ganancias (español)", err is None, (err or "")[:300])
e = db.query_one("SELECT * FROM reservas WHERE codigo_confirmacion='HMES001'") or {}
chk("ES: fecha 25/08/2026", str(e.get("fecha_inicio"))[:10] == "2026-08-25", e.get("fecha_inicio"))
chk("ES: bruto 120.000 y neto 116.400", e.get("ingreso_bruto") == 120000 and e.get("ingreso_neto") == 116400,
    (e.get("ingreso_bruto"), e.get("ingreso_neto")))
chk("ES: moneda ARS, noches 2", e.get("moneda") == "ARS" and e.get("noches") == 2)
chk("ES: 'Pago' no cuenta como error", "filas con errores" not in (h or ""), re.findall(r"\d+ filas con errores", h or ""))

# ── páginas con datos ──
for p in ("/", "/propiedades", f"/propiedades/{P1}", "/precios", "/competencia", "/informes"):
    resp = c.get(p)
    hh = resp.get_data(as_text=True)
    chk(f"con datos {p} → {resp.status_code}", resp.status_code in (200, 404) and "Traceback" not in hh)
hh = c.get("/?desde=2026-01-01&hasta=2026-12-31").get_data(as_text=True)
chk("dashboard: próximas con fecha argentina", "20/12/2026" in hh)
chk("dashboard: sin decimales con punto", not re.search(r"\d\.\d+%|\d\.\d+ noches", hh), re.findall(r".{20}\d\.\d+ ?(?:%|noches).{5}", hh)[:3])
print("FALLAS:", fallas)
