# ### CAMBIO AQUÍ ### PRUEBA AUTOMÁTICA — ¡BORRA LA BASE QUE USA!
# Solo corre con PRUEBAS_OK=1 y una base local (PRUEBAS_DATABASE_URL en localhost). Nunca la de Render o Neon.
import os as _os, sys as _sys
from urllib.parse import urlsplit as _us
_U = _os.environ.get("PRUEBAS_DATABASE_URL", "")
if not _U or (_us(_U).hostname or "") not in ("", "localhost", "127.0.0.1") or _os.environ.get("PRUEBAS_OK") != "1":
    _sys.exit("Estas pruebas BORRAN la base: solo corren con PRUEBAS_OK=1 y PRUEBAS_DATABASE_URL apuntando a una base local.")
import os, sys, io, re, json, warnings
warnings.filterwarnings("ignore"); sys.path.insert(0, sys.argv[1])
os.environ.update(DATABASE_URL=_U, GROQ_API_KEY="x", SECRET_KEY="clave-de-prueba-larga-123", ADMIN_USER="adriano", ADMIN_PASS="prueba-segura-123")
import psycopg2
c0=psycopg2.connect(os.environ["DATABASE_URL"]); c0.autocommit=True
c0.cursor().execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"); c0.close()
import app as A, database as db, monedas
A.app.config["PROPAGATE_EXCEPTIONS"]=True
c=A.app.test_client(); c.post("/login",data={"usuario":"adriano","password":"prueba-segura-123"})
def chk(n,cond,x=""): print(("OK " if cond else "XX ")+n, x)
txt=lambda r: re.sub(r"\s+"," ",r.get_data(as_text=True))
c.post("/propiedades/nueva",data={"nombre":"Depto Palermo Alto","barrio":"Palermo","tipo":"depto","ambientes":"2","capacidad":"4","precio_base":"120","moneda":"USD","costo_expensas":"300","rating":"4.9","reviews_count":"40"})
c.post("/propiedades/nueva",data={"nombre":"Studio Villa Crespo","barrio":"Villa Crespo","tipo":"depto","ambientes":"1","capacidad":"2","precio_base":"130000","moneda":"ARS","costo_expensas":"420000"})
p1,p2=[x["id"] for x in db.query("SELECT id FROM propiedades ORDER BY nombre")]
chk("moneda guardada", [x["moneda"] for x in db.query("SELECT moneda FROM propiedades ORDER BY nombre")]==["USD","ARS"])
r=c.get("/propiedades"); t=txt(r); chk("lista con monedas", "US$ 120" in t and "$ 130.000" in t)
# CSV: one with Moneda column, the other without (uses property currency)
csv1="Código de confirmación,Fecha de inicio,Fecha de finalización,Noches,Anuncio,Moneda,Ingresos netos,Cantidad\nA1,2026-09-02,2026-09-05,3,Palermo,USD,350,360\nA2,2026-09-10,2026-09-12,2,Villa,,250000,260000\n"
c.post("/importar",data={"csv_file":(io.BytesIO(csv1.encode()),"x.csv")},content_type="multipart/form-data")
c.post("/importar/asignar",data={"asignar":"1","prop_0":p1,"prop_1":p2})
m={x["codigo_confirmacion"]:x["moneda"] for x in db.query("SELECT * FROM reservas")}
chk("moneda de reservas", m=={"A1":"USD","A2":"ARS"}, m)
# sin TC -> aviso
r=c.get("/?desde=2026-09-01&hasta=2026-09-30"); t=txt(r)
chk("sin TC avisa", "no se sumaron" in t and "Cargar tipo de cambio" in t)
c.post("/tipo-cambio",data={"valor":"1.400"}); chk("TC manual 1.400", monedas.tc_valor()==1400.0)
c.post("/tipo-cambio",data={"valor":"1400,5"}); chk("TC manual 1400,5", monedas.tc_valor()==1400.5)
c.post("/tipo-cambio",data={"valor":"1400"})
r=c.get("/?desde=2026-09-01&hasta=2026-09-30"); t=txt(r)
# ARS: 360*1400=504000 + 260000 = 764000 bruto
chk("dashboard en ARS", "$ 764.000" in t and "no se sumaron" not in t, re.findall(r"stat-num\">([^<]+)<",t)[:6])
c.get("/moneda/USD"); r=c.get("/?desde=2026-09-01&hasta=2026-09-30"); t=txt(r)
chk("dashboard en USD", "US$ 546" in t, re.findall(r"stat-num\">([^<]+)<",t)[:6])
# competencia mixta para Palermo (USD prop)
for pz,mon in [(130,"USD"),(150,"USD"),(168000,"ARS")]:
    db.execute("INSERT INTO competencia (propiedad_id,barrio,tipo,precio_noche,moneda,rating,fecha,origen) VALUES (%s,'Palermo','depto',%s,%s,4.8,'2026-10-07','ia')",(p1,pz,mon))
r=c.get(f"/competencia?pid={p1}"); t=txt(r)
chk("competencia stats en USD (prop)", "US$ 130" in t and "US$ 150" in t and "≈ US$ 120" in t, re.findall(r"stat-num\">([^<]+)<",t))
r=c.post("/precios",data={"propiedad_id":p1,"fecha":"2026-12-12"}); t=txt(r)
chk("precio en USD + equivalente ARS", re.search(r'Sugerido</span><strong>US\$ \d+',t) is not None and "≈ $" in t, re.findall(r'precio-num">([^<]+)<',t))
# borrar TC -> competencia con aviso
db.execute("DELETE FROM config WHERE clave='tipo_cambio'")
r=c.get(f"/competencia?pid={p1}"); chk("sin TC: aviso en competencia", "en otra moneda" in txt(r))
# traer TC (mock)
class FR:
    def raise_for_status(s): pass
    def json(s): return {"venta": 1455.0, "compra": 1430}
monedas.requests.get=lambda url, timeout: FR() if url.endswith("/bolsa") else (_ for _ in ()).throw(Exception("x"))
r=c.post("/tipo-cambio",data={"tipo":"bolsa"},follow_redirects=True); chk("traer MEP", monedas.tc_valor()==1455.0 and "Dólar MEP" in txt(r))
# asistente contexto
import asistente_route as AR
conn=db.get_db()
try: ctx=AR.build_context(conn); chk("contexto asistente por moneda", "En USD" in ctx and "En ARS" in ctx and "Total convertido" in ctx and "US$ 120" in ctx)
finally: db._release(conn)
print([l for l in ctx.splitlines() if "En " in l or "Total conv" in l or "anuncios similares" in l])
# competencia_ia limpieza mixta
import competencia_ia as ci
l=ci.limpiar_comparables([{"link":"https://a","precio_noche":"55.000","moneda":"ARS"},{"link":"https://b","precio_noche":60,"moneda":"usd"},{"link":"https://c","precio_noche":60,"moneda":"ARS"}])
chk("limpiar mixto", [(x["precio_noche"],x["moneda"]) for x in l]==[(55000.0,"ARS"),(60.0,"USD")], l)
# informe usa moneda
captured={}
import ia
ia.generar_informe=lambda m, **k: captured.update(m) or "## Resumen"
c.post("/informes/generar",data={"desde":"2026-09-01","hasta":"2026-09-30"})
chk("informe recibe moneda", "dólares" in captured.get("moneda",""), captured.get("moneda"))
for u in ["/","/propiedades","/importar","/precios","/asistente","/informes","/competencia",f"/propiedades/{p1}/editar"]:
    r=c.get(u); chk("GET "+u, r.status_code==200)
