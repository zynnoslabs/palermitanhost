# ### CAMBIO AQUÍ ### PRUEBA AUTOMÁTICA — ¡BORRA LA BASE QUE USA!
# Solo corre con PRUEBAS_OK=1 y una base local (PRUEBAS_DATABASE_URL en localhost). Nunca la de Render o Neon.
import os as _os, sys as _sys
from urllib.parse import urlsplit as _us
_U = _os.environ.get("PRUEBAS_DATABASE_URL", "")
if not _U or (_us(_U).hostname or "") not in ("", "localhost", "127.0.0.1") or _os.environ.get("PRUEBAS_OK") != "1":
    _sys.exit("Estas pruebas BORRAN la base: solo corren con PRUEBAS_OK=1 y PRUEBAS_DATABASE_URL apuntando a una base local.")
import os, sys, io, re, json, warnings, logging
from datetime import date, timedelta
warnings.filterwarnings("ignore"); sys.path.insert(0, sys.argv[1])
os.environ.update(DATABASE_URL=_U, GROQ_API_KEY="x", SECRET_KEY="clave-de-prueba-larga-123", ADMIN_USER="adriano", ADMIN_PASS="prueba-segura-123")
import psycopg2
c0=psycopg2.connect(os.environ["DATABASE_URL"]); c0.autocommit=True
c0.cursor().execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"); c0.close()
import app as A, database as db, ia
A.app.config["PROPAGATE_EXCEPTIONS"]=True
c=A.app.test_client(); c.post("/login",data={"usuario":"adriano","password":"prueba-segura-123"})
def chk(name, cond, extra=""): print(("OK " if cond else "XX ")+name, extra)
r=c.post("/propiedades/nueva",data={"nombre":"Depto Palermo Alto","barrio":"Palermo","tipo":"depto","ambientes":"2","capacidad":"4","precio_base":"120","estado":"activa"})
c.post("/propiedades/nueva",data={"nombre":"Studio Villa Crespo","barrio":"Villa Crespo","tipo":"depto","ambientes":"1","capacidad":"2","precio_base":"95","estado":"mantenimiento"})
p1,p2=[x["id"] for x in db.query("SELECT id FROM propiedades ORDER BY nombre")]
t=date.today()
f=lambda d: (t+timedelta(days=d)).isoformat()
reservas_csv = "\n".join([
 "Código de confirmación,Estado,Nombre del huésped,Contacto,Fecha de inicio,Fecha de finalización,N.º de noches,Reservada,Anuncio,Ingresos",
 f"HMA1,Confirmada,María González,+54,{f(2)},{f(5)},3,{f(-20)},Depto Palermo Alto,\"360,00\"",
 f"HMA2,Pendiente,James King,+1,{f(9)},{f(14)},5,{f(-3)},Depto Palermo Alto,600.00",
 f"HMA3,Cancelada por el huésped,Sofía R,+54,{f(15)},{f(17)},2,{f(-1)},Studio Villa Crespo,190",
 f"HMA4,Huésped actual,Luca M,+39,{f(-2)},{f(3)},5,{f(-40)},Studio Villa Crespo,475",
])
r=c.post("/importar",data={"csv_file":(io.BytesIO(reservas_csv.encode()),"res.csv")},content_type="multipart/form-data",follow_redirects=True)
chk("import export Reservas -> paso 3", "Asignar anuncios" in r.text)
r=c.post("/importar/asignar",data={"asignar":"1","prop_0":p1,"prop_1":p2},follow_redirects=True)
chk("import guarda 4", db.query_one("SELECT COUNT(*) n FROM reservas")["n"]==4, re.findall(r"\d+ reservas nuevas[^<]*",r.text)[:1])
rows={x["codigo_confirmacion"]:x for x in db.query("SELECT * FROM reservas")}
chk("huésped/estado/anticipación", rows["HMA1"]["huesped_nombre"]=="María González" and rows["HMA2"]["estado"]=="pendiente" and rows["HMA3"]["estado"]=="cancelada" and rows["HMA1"]["anticipacion_dias"]==22, (rows["HMA1"]["ingreso_bruto"], rows["HMA4"]["estado"]))
# re-import same -> updates not duplicates
c.post("/importar",data={"csv_file":(io.BytesIO(reservas_csv.encode()),"res.csv")},content_type="multipart/form-data")
r=c.post("/importar/asignar",data={"asignar":"1","prop_0":p1,"prop_1":p2},follow_redirects=True)
chk("reimportar no duplica", db.query_one("SELECT COUNT(*) n FROM reservas")["n"]==4, re.findall(r"\d+ reservas nuevas[^<]*",r.text)[:1])
# dashboard
db.execute("INSERT INTO resenas (propiedad_id,texto,pendiente) VALUES (%s,'Muy lindo',1),(%s,'Ok',0)",(p1,p1))
r=c.get("/"); h=r.text
px=h.split("Próximas reservas",1)[1].split("</table>",1)[0]
chk("dashboard próximas reservas", "María González" in px and "James King" in px and "Sofía R" not in px)
chk("dashboard reseñas pendientes", re.search(r'stat-num">1</div>\s*<div class="stat-lbl">Reseñas pendientes',h) is not None)
o=json.loads(re.search(r"const ocup7 = (\[.*?\]);",h).group(1)); chk("ocupación 7 días", len(o)==7 and o[-1]["pct"]==50 and o[-3]["pct"]==50 and o[-4]["pct"]==0, [d["pct"] for d in o])
r=c.get(f"/?propiedad_id={p1}"); chk("dashboard filtrado", "María González" in r.text and "Luca M" not in r.text)
# propiedades
r=c.get(f"/propiedades?ver={p2}"); chk("propiedades estado+huéspedes", "Mantenimiento" in r.text and "Luca M" in r.text and "María González" not in r.text)
r=c.post(f"/propiedades/{p2}/editar",data={"nombre":"Studio Villa Crespo","barrio":"Villa Crespo","estado":"activa","tipo":"depto"},follow_redirects=True)
chk("editar estado", db.query_one("SELECT estado FROM propiedades WHERE id=%s",(p2,))["estado"]=="activa")
r=c.get(f"/propiedades/{p1}/editar"); chk("form muestra estado", 'name="estado"' in r.text)
# asistente tabs
for tab in ["negocio","huespedes","resenas"]:
    r=c.get(f"/asistente?tab={tab}"); chk("asistente "+tab, r.status_code==200)
ia.responder_huesped=lambda *a,**k: ("Voy a consultar con el anfitrión y te respondo a la brevedad.", True)
r=c.post("/asistente",data={"propiedad_id":p1,"mensaje":"¿Hay cochera?"},follow_redirects=True); chk("consulta pendiente", "Guardar y marcar respondida" in r.text)
cid=db.query_one("SELECT id FROM consultas_huespedes")["id"]
c.post(f"/asistente/consulta/{cid}/responder",data={"respuesta":"No hay cochera, pero hay una a 1 cuadra."})
chk("responder consulta", db.query_one("SELECT pendiente FROM consultas_huespedes")["pendiente"]==0)
ia.responder_resena=lambda *a,**k: "¡Gracias por tu reseña!"
c.post("/resenas/nueva",data={"propiedad_id":p1,"huesped":"Ana","puntaje":"5","texto":"Excelente ubicación"})
r=c.get("/asistente?tab=resenas"); chk("reseña con borrador IA", "¡Gracias por tu reseña!" in r.text and "Excelente ubicación" in r.text)
rid=db.query_one("SELECT id FROM resenas WHERE huesped='Ana'")["id"]
c.post(f"/resenas/{rid}/responder",data={"respuesta":"Gracias Ana!"}); chk("marcar reseña", db.query_one("SELECT pendiente FROM resenas WHERE id=%s",(rid,))["pendiente"]==0)
# chat negocio con historial
import asistente_route as AR
class R:
    def __init__(s,t): s.choices=[type("C",(),{"message":type("M",(),{"content":t})()})()]
class FakeG:
    def __init__(s,**k): pass
    chat=type("Ch",(),{"completions":type("Co",(),{"create":lambda s,**k: R("Este mes ganaste X.")})()})()
AR.Groq=FakeG; ia.Groq=FakeG
r=c.post("/asistente/chat",json={"mensaje":"¿Cuánto gané?"}); chk("chat negocio", r.get_json()["respuesta"]=="Este mes ganaste X.")
r=c.get("/asistente?tab=negocio"); chk("historial chat visible", "Este mes ganaste X." in r.text and "¿Cuánto gané?" in r.text)
c.post("/asistente/limpiar"); chk("limpiar chat", AR._cargar_historial()==[])
chk("cookie chica", all(len(h)<1500 for h in r.headers.getlist("Set-Cookie")))
r=c.post(f"/propiedades/{p1}/eliminar",follow_redirects=True); chk("no borra con reservas", "No se puede eliminar" in r.text)
