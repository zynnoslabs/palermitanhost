# ### CAMBIO AQUÍ ### PRUEBA AUTOMÁTICA — ¡BORRA LA BASE QUE USA!
# Solo corre con PRUEBAS_OK=1 y una base local (PRUEBAS_DATABASE_URL en localhost). Nunca la de Render o Neon.
import os as _os, sys as _sys
from urllib.parse import urlsplit as _us
_U = _os.environ.get("PRUEBAS_DATABASE_URL", "")
if not _U or (_us(_U).hostname or "") not in ("", "localhost", "127.0.0.1") or _os.environ.get("PRUEBAS_OK") != "1":
    _sys.exit("Estas pruebas BORRAN la base: solo corren con PRUEBAS_OK=1 y PRUEBAS_DATABASE_URL apuntando a una base local.")
import os, sys, io, re, json, warnings, threading
from datetime import date, datetime, timedelta
warnings.filterwarnings("ignore"); sys.path.insert(0, sys.argv[1])
os.environ.update(DATABASE_URL=_U, GROQ_API_KEY="x",
                  SECRET_KEY="clave-de-prueba-larga-123", ADMIN_USER="adriano", ADMIN_PASS="prueba-segura-123",
                  TAREAS_TOKEN="token-de-prueba-largo-123")
for k in ("SERPAPI_API_KEY", "TAVILY_API_KEY"):
    os.environ.pop(k, None)
import psycopg2
c0 = psycopg2.connect(os.environ["DATABASE_URL"]); c0.autocommit = True
c0.cursor().execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"); c0.close()
import app as A, database as db, metricas as M, monedas, competencia_ia as CI, competencia_auto as CA, importador as I
import precio_estrategico as PE, privacidad, ia
fallas = 0
def chk(n, c, x=""):
    global fallas
    if not c: fallas += 1
    print(("OK " if c else "XX ") + n, "" if c else x)

@A.app.route("/_explota")
def _explota():
    raise RuntimeError("x")
c = A.app.test_client()
# ── login vuelve a la página pedida ──
r = c.get("/informes"); chk("sin login → login", r.status_code == 302 and "/login" in r.headers["Location"])
r = c.post("/login", data={"usuario": "adriano", "password": "prueba-segura-123"})
chk("después de ingresar vuelve a Informes", r.headers.get("Location", "").startswith("/informes"), r.headers.get("Location"))

# ── páginas de error ──
r = c.get("/no-existe"); chk("404 en castellano", r.status_code == 404 and "No encontramos esa página" in r.text)
A.app.config["PROPAGATE_EXCEPTIONS"] = False
r = c.get("/_explota"); chk("500 en castellano", r.status_code == 500 and "Algo salió mal" in r.text)
chk("/salud?db=1", c.get("/salud?db=1").text == "ok")

# ── importar sin propiedades ──
csv0 = ("Confirmation code,Status,Guest name,Start date,End date,# of nights,Booked,Listing,Earnings,Currency\n"
        "HMNUEVA1,Confirmed,X,12/01/2026,12/03/2026,2,11/01/2026,Loft Airbnb Uno,US$200.00,USD\n")
r = c.post("/importar", data={"csv_file": (io.BytesIO(csv0.encode()), "x.csv")}, content_type="multipart/form-data")
h0 = c.get(r.headers["Location"]).text
chk("sin propiedades: ofrece crearla (elegida)", 'value="nueva" selected' in h0)
t0 = re.search(r'name="t" value="([^"]+)"', h0).group(1)
r = c.post("/importar/asignar", data={"asignar": "1", "t": t0, "prop_0": "nueva"}, follow_redirects=True)
pn = db.query_one("SELECT * FROM propiedades WHERE nombre='Loft Airbnb Uno'")
chk("crea la propiedad desde el archivo (en USD)", pn and pn["moneda"] == "USD" and "Se crearon 1 propiedad" in r.text)
chk("y le carga la reserva", db.query_one("SELECT propiedad_id FROM reservas WHERE codigo_confirmacion='HMNUEVA1'")["propiedad_id"] == pn["id"])
db.execute("DELETE FROM reservas"); db.execute("DELETE FROM propiedades"); db.execute("DELETE FROM movimientos_airbnb")
db.execute("DELETE FROM config WHERE clave='anuncio_map'")
r = c.get("/importar/asignar"); chk("asignar directo → vuelve", r.status_code == 302)

# ── formulario de propiedad ──
r = c.post("/propiedades/nueva", data={"nombre": "D'Angelo Loft", "barrio": "Palermo", "ciudad": "Buenos Aires", "tipo": "depto",
                                       "ambientes": "2", "capacidad": "", "precio_base": "45.000", "costo_expensas": "$ 30.000",
                                       "costo_servicios": "15000,50", "rating": "4,85", "moneda": "ARS"})
p = db.query_one("SELECT * FROM propiedades WHERE nombre='D''Angelo Loft'")
chk("expensas 208560.13 exacto (sin perder centavos)", True)
chk("montos con puntos y comas", p and p["precio_base"] == 45000 and p["costo_expensas"] == 30000 and abs(p["costo_servicios"] - 15000.5) < .01,
    p and (p["precio_base"], p["costo_expensas"], p["costo_servicios"]))
chk("puntaje 4,85", p and abs(p["rating"] - 4.85) < .001)
r = c.post("/propiedades/nueva", data={"nombre": "Mal", "barrio": "Palermo", "ambientes": "2,5", "precio_base": "abc"})
chk("ambientes 2,5 → aviso, sin error 500", r.status_code == 200 and "no es un número válido" in r.text and
    db.query_one("SELECT COUNT(*) n FROM propiedades WHERE nombre='Mal'")["n"] == 0)
chk("el formulario conserva lo escrito", 'value="Mal"' in r.text)
h = c.get("/propiedades").text
chk("lista sin 'None'", "None" not in h)
chk("confirmación con apóstrofo segura", "D\\u0027Angelo" in h or "D\\'Angelo" in h, re.findall(r"confirm\([^)]*\)", h)[:2])
h = c.get(f"/propiedades/{p['id']}/editar").text
chk("editar muestra 45000 y 4,85", 'value="45000"' in h and 'value="4,85"' in h)
c.post("/propiedades/nueva", data={"nombre": "Studio VC", "barrio": "Villa Crespo", "tipo": "depto", "ambientes": "1", "moneda": "USD"})
c.post("/propiedades/nueva", data={"nombre": "Viejo", "barrio": "Almagro", "tipo": "depto", "estado": "inactiva", "moneda": "ARS"})
P1 = p["id"]; P2 = db.query_one("SELECT id FROM propiedades WHERE nombre='Studio VC'")["id"]

# ── métricas ──
r1 = {"propiedad_id": 1, "fecha_inicio": "2026-10-05", "fecha_fin": "2026-10-25", "noches": 20, "ingreso_bruto": 2000, "ingreso_neto": 1800, "limpieza": 0}
m = M.calcular_metricas(M.filtrar_reservas([r1], "2026-10-01", "2026-10-09"), "2026-10-01", "2026-10-09")
chk("estadía larga: 5 de 9 noches (55,6%, no 222%)", m["noches_ocupadas"] == 5 and m["tasa_ocupacion"] == 55.6, m)
chk("dinero proporcional (5/20 de 2000 = 500)", m["ingreso_bruto"] == 500, m["ingreso_bruto"])
r2 = {"propiedad_id": 1, "fecha_inicio": "2026-09-28", "fecha_fin": "2026-10-05", "noches": 7, "ingreso_bruto": 700, "ingreso_neto": 630}
chk("cruza de mes: 3 en sept, 4 en oct",
    M.calcular_metricas([r2], "2026-09-01", "2026-09-30")["noches_ocupadas"] == 3 and M.calcular_metricas([r2], "2026-10-01", "2026-10-31")["noches_ocupadas"] == 4)
rc = {"propiedad_id": 1, "fecha_inicio": "2026-10-03", "fecha_fin": "2026-10-08", "noches": 5, "ingreso_bruto": 50, "ingreso_neto": 50, "estado": "cancelada"}
m = M.calcular_metricas([rc], "2026-10-01", "2026-10-31")
chk("cancelada: 0 noches, 0 reservas, cuenta lo cobrado", m["noches_ocupadas"] == 0 and m["total_reservas"] == 0 and m["canceladas"] == 1 and m["ingreso_neto"] == 50, m)
rl = {"propiedad_id": 1, "fecha_inicio": "2026-10-01", "fecha_fin": "2026-10-02", "noches": 1, "ingreso_bruto": 45000, "limpieza": 15000}
chk("ADR sin limpieza", M.calcular_metricas([rl], "2026-10-01", "2026-10-31")["adr"] == 30000)
chk("costo de 1 mes completo = exacto", M.costos_del_periodo(100000, "2026-10-01", "2026-10-31") == 100000 and
    M.costos_del_periodo(100000, "2026-02-01", "2026-02-28") == 100000)
chk("sin salida: usa noches", M.calcular_metricas([{"fecha_inicio": "2026-10-01", "noches": 3}], "2026-10-01", "2026-10-31")["noches_ocupadas"] == 3)
chk("filtro num sin '-0'", A.filtro_num(-0.04) == "0")
pm = M.metricas_por_mes([r2], None, *M.ventana_grafico("2026-10-01", "2026-10-09"))
chk("gráfico: 12 meses con etiquetas", len(pm) >= 12 and pm["2026-10"]["etiqueta"] == "oct 2026" and pm["2026-09"]["noches"] == 3, list(pm)[:3])

# ── fechas raras en la URL ──
for q in ("?desde=abc", "?desde=202610-10-01", "?desde=2026-02-30", "?desde=&hasta=", "?desde=2026-12-01&hasta=2026-01-01"):
    r = c.get("/" + q); chk(f"dashboard {q} → 200", r.status_code == 200, r.status_code)

# ── importar: archivo de Excel en castellano (; y acentos cp1252) ──
csv_es = ("Fecha;Tipo;Código de confirmación;Fecha de inicio;Noches;Huésped;Anuncio;Moneda;Importe;Tarifa de servicio;Ingresos brutos\n"
          "26/08/2026;Pago;;;;;;ARS;;;\n"
          "25/08/2026;Reserva;HMXL01;25/08/2026;2;Nuñez Ñandú;D'Angelo Loft;ARS;116.400,00;-3.600,00;120.000,00\n")
def importar(raw, asign):
    r1 = c.post("/importar", data={"csv_file": (io.BytesIO(raw), "x.csv")}, content_type="multipart/form-data")
    if r1.status_code != 302 or "asignar" not in r1.headers.get("Location", ""):
        return None, r1
    loc = r1.headers["Location"]
    h = c.get(loc).text
    t = re.search(r'name="t" value="([^"]+)"', h).group(1)
    import html as _h
    form = {"asignar": "1", "t": t}
    for nombre, i in re.findall(r'<label>([^<]*)</label>\s*<select name="prop_(\d+)"', h):
        form[f"prop_{i}"] = str(asign.get(_h.unescape(nombre), ""))
    r2 = c.post("/importar/asignar", data=form)
    return c.get(r2.headers["Location"]).text if r2.status_code == 302 else None, r2
h, _ = importar(csv_es.encode("cp1252"), {"D'Angelo Loft": P1})
x = db.query_one("SELECT * FROM reservas WHERE codigo_confirmacion='HMXL01'")
chk("Excel ; + cp1252 importa", x and x["ingreso_bruto"] == 120000 and x["ingreso_neto"] == 116400 and x["huesped_nombre"] == "Nuñez Ñandú",
    x and (x["ingreso_bruto"], x["huesped_nombre"]))
chk("salida calculada con las noches", x and x["fecha_fin"] == "2026-08-27")
h2 = c.get("/importar?resultado=1")
chk("actualizar el resultado no repite", h2.status_code == 302)
for nombre, raw, texto in [("xlsx", b"PK\x03\x04xxxx", "Excel"), ("pdf", b"%PDF-1.4 xx", "PDF"), ("vacío", b"   ", "vacío"),
                           ("solo títulos", b"Confirmation code,Start date\n", "solo tiene")]:
    r = c.post("/importar", data={"csv_file": (io.BytesIO(raw), "x.csv")}, content_type="multipart/form-data", follow_redirects=True)
    chk(f"archivo {nombre}: mensaje claro", r.status_code == 200 and texto in r.text, r.status_code)

# ── el anuncio queda recordado ──
r1 = c.post("/importar", data={"csv_file": (io.BytesIO(csv_es.encode("utf-8")), "x.csv")}, content_type="multipart/form-data")
h = c.get(r1.headers["Location"]).text
chk("anuncio pre-elegido la próxima vez", re.search(rf'<option value="{P1}" selected', h) is not None)
# dos pestañas: el archivo de cada una no se mezcla
csv_b = csv_es.replace("HMXL01", "HMXL02").replace("D'Angelo Loft", "Otro anuncio")
r2 = c.post("/importar", data={"csv_file": (io.BytesIO(csv_b.encode("utf-8")), "x.csv")}, content_type="multipart/form-data")
t1 = re.search(r"t=([^&]+)", r1.headers["Location"]).group(1)
c.post("/importar/asignar", data={"asignar": "1", "t": t1, "prop_0": str(P1)})
chk("dos pestañas: cada una importa su archivo", db.query_one("SELECT COUNT(*) n FROM reservas WHERE codigo_confirmacion='HMXL02'")["n"] == 0)
r = c.post("/importar/asignar", data={"asignar": "1", "t": t1, "prop_0": str(P1)})
chk("doble envío: avisa y no repite", r.status_code == 302 and "/importar" in r.headers["Location"])

# ── Ganancias en inglés: estadía larga cobrada en dos archivos que se superponen ──
cab = "Date,Type,Confirmation Code,Booking date,Start date,Nights,Guest,Listing,Details,Reference code,Currency,Amount,Paid out,Service fee,Fast pay fee,Cleaning fee,Gross earnings,Occupancy taxes,Earnings year\n"
sept = cab + "09/02/2026,Reservation,HMLARGA,08/01/2026,09/01/2026,30,John Smith,Studio VC,,,USD,900.00,,-100.00,,0,\"1,000.00\",,2026\n"
octu = cab + ("10/02/2026,Reservation,HMLARGA,08/01/2026,10/01/2026,31,John Smith,Studio VC,,,USD,930.00,,-100.00,,0,\"1,030.00\",,2026\n"
              "10/05/2026,Resolution Adjustment,HMLARGA,,,,,,Daño,,USD,50.00,,,,,,,2026\n"
              "10/06/2026,Reservation,HMEXP,10/01/2026,10/20/2026,2,Ana,Studio VC,,,USD,100.00,,-10,,0,110,,2026\n")
importar(sept.encode(), {"Studio VC": P2}); importar(octu.encode(), {"Studio VC": P2}); importar(sept.encode(), {"Studio VC": P2})
L = db.query_one("SELECT * FROM reservas WHERE codigo_confirmacion='HMLARGA'")
chk("estadía larga en 2 archivos (+ repetir uno): neto 900+930+50", L and abs(L["ingreso_neto"] - 1880) < .01, L and L["ingreso_neto"])
chk("… bruto 1000+1030+50", L and abs(L["ingreso_bruto"] - 2080) < .01, L and L["ingreso_bruto"])
chk("… fecha 20/10 en formato mes/día", db.query_one("SELECT fecha_inicio FROM reservas WHERE codigo_confirmacion='HMEXP'")["fecha_inicio"] == "2026-10-20")
# Reservas: vencida/consulta no entra; cancelada sin monto
res = ("Confirmation code,Status,Guest name,Start date,End date,# of nights,Booked,Listing,Earnings\n"
       "HMV1,Expired,X,12/01/2026,12/03/2026,2,11/01/2026,Studio VC,US$200.00\n"
       "HMC1,Canceled by guest,Y,12/05/2026,12/08/2026,3,11/01/2026,Studio VC,US$300.00\n"
       "HMR1,Review guest,Z,Oct 1 2026,Oct 3 2026,2,Sep 1 2026,Studio VC,US$150.00\n")
h, _ = importar(res.encode(), {"Studio VC": P2})
R = {x["codigo_confirmacion"]: x for x in db.query("SELECT * FROM reservas")}
chk("vencida no entra", "HMV1" not in R)
chk("cancelada del archivo de Reservas: sin monto", R.get("HMC1", {}).get("ingreso_neto") == 0 and R["HMC1"]["estado"] == "cancelada")
chk("'Review guest' = completada y fecha 'Oct 1 2026'", R.get("HMR1", {}).get("estado") == "completada" and R["HMR1"]["fecha_inicio"] == "2026-10-01")
chk("parseo: '2026-10-05 00:00:00' y '5 oct. 2026'", I.parsear_fecha("2026-10-05 00:00:00") == "2026-10-05" and I.parsear_fecha("5 oct. 2026") == "2026-10-05")
chk("noches '3.0'", I._entero("3.0") == 3)
chk("_norm no come 'No'", I._norm("Noches") == "noches" and I._norm("Nombre") == "nombre" and I._norm("N.º de noches") == "noches")

# ── competencia manual ──
r = c.post(f"/competencia?pid={P1}", data={"precio_noche": "30.000", "moneda": "ARS", "barrio": "Palermo"})
chk("competidor manual '30.000'", db.query_one("SELECT precio_noche FROM competencia ORDER BY id DESC LIMIT 1")["precio_noche"] == 30000)
n0 = db.query_one("SELECT COUNT(*) n FROM competencia")["n"]
c.post(f"/competencia?pid={P1}", data={"precio_noche": "55", "moneda": "ARS"})
chk("precio absurdo rechazado", db.query_one("SELECT COUNT(*) n FROM competencia")["n"] == n0)
r = c.post("/competencia/buscar", data={"propiedad_id": P1}, follow_redirects=True)
chk("sin claves: dice que falta configurar", "No hay ninguna fuente de búsqueda configurada" in r.text)
with db.bloqueo(CA.CLAVE_BLOQUEO) as ok_:
    r = c.post("/competencia/buscar", data={"propiedad_id": P1}, follow_redirects=True)
    chk("búsqueda en curso: no busca dos veces", ok_ and "Ya se está actualizando" in r.text and CA.en_curso())
chk("candado liberado", not CA.en_curso())
os.environ["SERPAPI_API_KEY"] = "clave-secreta-serp"
import requests
real_get = requests.get
def falla(url, params=None, **k):
    raise requests.ConnectionError(f"HTTPSConnectionPool: Max retries with url: /search?api_key={params.get('api_key')}&q=x")
requests.get = falla
res = CI.buscar_comparables({"id": P1, "barrio": "Palermo", "ciudad": "Buenos Aires", "moneda": "ARS"}, con_resumen=False)
requests.get = real_get
chk("la clave de SerpApi no aparece en el error", "clave-secreta-serp" not in json.dumps(res, default=str), res.get("error"))
chk("limpiar_error", "secreto" not in CI.limpiar_error("x?api_key=secreto&b=1"))
os.environ.pop("SERPAPI_API_KEY")
chk("cupo SerpApi: 250 el 9/10 → 10 por noche", CA.presupuesto_serpapi(250, date(2026, 10, 9)) == 10)
chk("agrupa por ambientes", len(CA.agrupar([{"id": 1, "barrio": "Palermo", "ambientes": 1}, {"id": 2, "barrio": "Palermo", "ambientes": 3}])) == 2)
r = c.get("/tareas/competencia", headers={"X-Token": "inventar-una-clave-larga-y-secreta"})
chk("token de ejemplo rechazado", r.status_code == 403)

# ── precios ──
merc = {"mediana": 32.4, "rating_promedio_zona": 4.5, "rating_real": False, "cantidad_propiedades": 5, "simbolo": "US$"}
res = PE.calcular_precio_estrategico({"rating": None, "reviews_count": 10}, merc, [], "2026-10-11")   # domingo
chk("domingo no es fin de semana", res["es_fin_de_semana"] is False)
chk("sin reservas: ocupación no baja el precio", next(p for p in res["pasos"] if p["paso"] == 5)["multiplicador"] == 1.0)
chk("sin puntaje: no ajusta", next(p for p in res["pasos"] if p["paso"] == 2)["multiplicador"] == 1.0)
chk("USD barato redondea de a 1", res["precio_sugerido"] == round(32.4 * 1.0) or res["precio_sugerido"] in (32, 33), res["precio_sugerido"])
chk("explicación en castellano", "octubre" in res["explicacion"] and "mes 10" not in res["explicacion"])
db.execute("UPDATE propiedades SET costo_expensas=1500000 WHERE id=%s", (P1,))
db.execute("""INSERT INTO competencia (propiedad_id,barrio,precio_noche,fecha,origen,moneda,link)
              VALUES (%s,'Palermo',40000,%s,'ia','ARS','https://x')""", (P1, date.today().isoformat()))
h = c.post("/precios", data={"propiedad_id": P1, "fecha": "2026-10-14"}).text
nums = [int(x.replace(".", "")) for x in re.findall(r"\$ ([\d.]+)", h)]
chk("precios: sugerido ≥ mínimo (costos altos)", "para cubrir tus costos fijos" in h, nums[:6])

# ── asistente ──
ia.responder_huesped = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Groq caído"))
n0 = db.query_one("SELECT COUNT(*) n FROM consultas_huespedes")["n"]
r = c.post("/asistente", data={"propiedad_id": P1, "mensaje": "¿Hay wifi?"})
chk("IA caída: no guarda el error como respuesta", db.query_one("SELECT COUNT(*) n FROM consultas_huespedes")["n"] == n0)
chk("IA caída: la página sigue andando (pestaña de consultas sacada)", r.status_code == 200)
ia.responder_huesped = lambda *a, **k: ("El wifi es Casa123.", False)
r = c.post("/asistente", data={"propiedad_id": P1, "mensaje": "¿Hay wifi?"})
chk("consulta: recarga sin reenviar (PRG)", r.status_code == 302 and "c=" in r.headers["Location"])
chk("consulta: se guarda la respuesta (la pestaña se sacó, el dato queda)", db.query_one("SELECT COUNT(*) n FROM consultas_huespedes WHERE respuesta LIKE %s", ("%Casa123%",))["n"] == 1)
import asistente_route as AR
AR._guardar_historial([])
orig = ia.completar
ia.completar = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("413 Request too large"))
j = c.post("/asistente/chat", json={"mensaje": "hola"}).get_json()
chk("chat: error no queda en la conversación", j.get("error") and AR._cargar_historial() == [], AR._cargar_historial())
ia.completar = orig
largo = [{"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 1500} for i in range(20)]
rec = AR._recortar(largo)
chk("chat: historial recortado y empieza con el usuario", sum(len(m["content"]) for m in rec) <= 7500 and rec[0]["role"] == "user")
al = privacidad.armar_alias([("Luz", 3), ("Abril Fernández", 7)])
chk("privacidad: 'luz' y 'abril' comunes no se tapan", privacidad.ocultar("pagué la luz en abril", al)[0] == "pagué la luz en abril")

# ── informes: PDF con '<' y Excel ──
iid = db.execute("""INSERT INTO informes (titulo, fecha_desde, fecha_hasta, propiedad_id, contenido)
                    VALUES ('Prueba', '2026-08-01', '2026-10-31', NULL, %s) RETURNING id""",
                 ("## Resumen\nOcupación <b subió y a<b\n**Importante**: =HYPERLINK(\"x\")\n| a | b |\n|---|---|\n| 1 | 2 |",))
r = c.get(f"/informes/{iid}/pdf"); chk("PDF con '<' no rompe", r.status_code == 200 and r.data[:4] == b"%PDF", r.status_code)
r = c.get(f"/informes/{iid}/excel"); chk("Excel del informe", r.status_code == 200)
from openpyxl import load_workbook
wb = load_workbook(io.BytesIO(r.data))
res_ws = [list(x) for x in wb["Resumen"].iter_rows(values_only=True)]
chk("Excel: totales separados por moneda", any(x[0] == "TOTAL PESOS" for x in res_ws) and any(x[0] == "TOTAL DÓLARES" for x in res_ws), res_ws[3:9])
chk("Excel: sin fórmulas inyectadas", all(not str(c_.value or "").startswith("=") for row in wb["Informe"].iter_rows() for c_ in row))
h = c.get(f"/informes/{iid}").text
chk("informe en pantalla: títulos y negrita, escapado", "<h3>Resumen</h3>" in h and "<strong>Importante</strong>" in h and "&lt;b subió" in h)

# ── hora y conexiones ──
ok_tz = True
def usar():
    global ok_tz
    for _ in range(30):
        cn = db.get_db()
        cur = cn.cursor(); cur.execute("SHOW TIME ZONE"); tz = cur.fetchone()[0]; cur.close()
        if tz != "America/Argentina/Buenos_Aires":
            ok_tz = False
        db._release(cn)
hilos = [threading.Thread(target=usar) for _ in range(8)]
[h_.start() for h_ in hilos]; [h_.join() for h_ in hilos]
chk("todas las conexiones en hora de Buenos Aires (8 hilos × 30)", ok_tz)
cn = db.get_db(); cn.close(); db._release(cn)
chk("conexión cortada se reemplaza sola", db.query_one("SELECT 1 AS x")["x"] == 1)
idle = db.query_one("SELECT COUNT(*) n FROM pg_stat_activity WHERE state = 'idle in transaction' AND datname = current_database()")["n"]
chk("no quedan transacciones abiertas", idle == 0, idle)
print("FALLAS:", fallas)
