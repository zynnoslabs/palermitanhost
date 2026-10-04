# app.py
import os
import json
from datetime import datetime, date
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, jsonify)
from dotenv import load_dotenv

load_dotenv()

import database as db
import importador
import metricas as met
import precios as prec
import ia

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "cambiar-esto-en-produccion")

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin123")

# ── Blueprints ───────────────────────────────────────────────────────────────
from asistente_route import asistente_bp
from exportar_routes import exportar_bp
from ruta_precios    import precios_bp

app.register_blueprint(asistente_bp)
app.register_blueprint(exportar_bp)
app.register_blueprint(precios_bp)

# ── Inicializar DB al arrancar ───────────────────────────────────────────────
with app.app_context():
    db.init_db()


# ── Decorador de login ───────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ════════════════════════════════════════════════════════════════════════════
# LOGIN
# ════════════════════════════════════════════════════════════════════════════

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        if (request.form.get("usuario") == ADMIN_USER and
                request.form.get("password") == ADMIN_PASS):
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        flash("Usuario o contraseña incorrectos.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ════════════════════════════════════════════════════════════════════════════

@app.route("/")
@login_required
def dashboard():
    propiedades = db.query("SELECT * FROM propiedades ORDER BY nombre")

    hasta  = request.args.get("hasta",  date.today().isoformat())
    desde  = request.args.get("desde",  date(date.today().year, date.today().month, 1).isoformat())
    prop_id = request.args.get("propiedad_id", None, type=int)

    reservas = db.query("SELECT * FROM reservas")
    reservas_filtradas = met.filtrar_reservas(reservas, desde, hasta, prop_id)

    costos_mes = 0
    if prop_id:
        p = db.query_one("SELECT * FROM propiedades WHERE id=%s", (prop_id,))
        if p:
            costos_mes = sum([
                p.get("costo_expensas",0) or 0,
                p.get("costo_servicios",0) or 0,
                p.get("costo_limpieza",0) or 0,
                p.get("costo_comision",0) or 0,
            ])

    stats = met.calcular_metricas(reservas_filtradas, desde, hasta, costos_mes)
    por_mes = met.metricas_por_mes(reservas_filtradas, prop_id)

    informes = db.query("SELECT id, titulo, creado_en FROM informes ORDER BY creado_en DESC LIMIT 5")

    return render_template("dashboard.html",
        propiedades=propiedades, stats=stats, por_mes=json.dumps(por_mes),
        desde=desde, hasta=hasta, prop_id=prop_id, informes=informes)


# ════════════════════════════════════════════════════════════════════════════
# PROPIEDADES
# ════════════════════════════════════════════════════════════════════════════

@app.route("/propiedades")
@login_required
def propiedades():
    props = db.query("SELECT * FROM propiedades ORDER BY nombre")
    return render_template("propiedades.html", propiedades=props)


@app.route("/propiedades/nueva", methods=["GET","POST"])
@login_required
def nueva_propiedad():
    if request.method == "POST":
        f = request.form
        db.execute("""
            INSERT INTO propiedades
            (nombre,direccion,barrio,tipo,ambientes,capacidad,precio_base,
             costo_expensas,costo_servicios,costo_limpieza,costo_comision,info_huespedes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            f.get("nombre"), f.get("direccion"), f.get("barrio"), f.get("tipo"),
            f.get("ambientes") or None, f.get("capacidad") or None,
            f.get("precio_base") or 0,
            f.get("costo_expensas") or 0, f.get("costo_servicios") or 0,
            f.get("costo_limpieza") or 0, f.get("costo_comision") or 0,
            f.get("info_huespedes","")
        ))
        flash("Propiedad creada correctamente.", "ok")
        return redirect(url_for("propiedades"))
    return render_template("propiedad_form.html", prop=None)


@app.route("/propiedades/<int:pid>/editar", methods=["GET","POST"])
@login_required
def editar_propiedad(pid):
    prop = db.query_one("SELECT * FROM propiedades WHERE id=%s", (pid,))
    if not prop:
        flash("Propiedad no encontrada.", "error")
        return redirect(url_for("propiedades"))
    if request.method == "POST":
        f = request.form
        db.execute("""
            UPDATE propiedades SET nombre=%s,direccion=%s,barrio=%s,tipo=%s,ambientes=%s,
            capacidad=%s,precio_base=%s,costo_expensas=%s,costo_servicios=%s,
            costo_limpieza=%s,costo_comision=%s,info_huespedes=%s
            WHERE id=%s
        """, (
            f.get("nombre"), f.get("direccion"), f.get("barrio"), f.get("tipo"),
            f.get("ambientes") or None, f.get("capacidad") or None,
            f.get("precio_base") or 0,
            f.get("costo_expensas") or 0, f.get("costo_servicios") or 0,
            f.get("costo_limpieza") or 0, f.get("costo_comision") or 0,
            f.get("info_huespedes",""), pid
        ))
        flash("Propiedad actualizada.", "ok")
        return redirect(url_for("propiedades"))
    return render_template("propiedad_form.html", prop=prop)


@app.route("/propiedades/<int:pid>/eliminar", methods=["POST"])
@login_required
def eliminar_propiedad(pid):
    db.execute("DELETE FROM propiedades WHERE id=%s", (pid,))
    flash("Propiedad eliminada.", "ok")
    return redirect(url_for("propiedades"))


# ════════════════════════════════════════════════════════════════════════════
# IMPORTAR CSV
# ════════════════════════════════════════════════════════════════════════════

@app.route("/importar", methods=["GET","POST"])
@login_required
def importar():
    propiedades = db.query("SELECT id, nombre FROM propiedades ORDER BY nombre")

    if request.method == "POST":
        archivo = request.files.get("csv_file")
        if not archivo or archivo.filename == "":
            flash("Seleccioná un archivo CSV.", "error")
            return redirect(url_for("importar"))

        contenido = archivo.read()
        import csv, io
        reader = csv.reader(io.StringIO(contenido.decode("utf-8-sig", errors="replace")))
        encabezados = next(reader, [])

        mapa, no_detectadas = importador.detectar_columnas(encabezados)

        session["csv_contenido"] = contenido.decode("utf-8-sig", errors="replace")
        session["csv_encabezados"] = encabezados
        session["csv_mapa"] = mapa
        session["csv_no_detectadas"] = no_detectadas

        if no_detectadas:
            return render_template("importar.html",
                propiedades=propiedades,
                paso=2,
                encabezados=encabezados,
                mapa=mapa,
                no_detectadas=no_detectadas)

        return redirect(url_for("importar_asignar"))

    return render_template("importar.html", propiedades=propiedades, paso=1)


@app.route("/importar/asignar", methods=["GET","POST"])
@login_required
def importar_asignar():
    propiedades = db.query("SELECT id, nombre FROM propiedades ORDER BY nombre")
    csv_contenido   = session.get("csv_contenido","")
    csv_encabezados = session.get("csv_encabezados",[])
    mapa            = session.get("csv_mapa",{})

    if request.method == "POST":
        for clave in session.get("csv_no_detectadas",[]):
            idx_str = request.form.get(f"col_{clave}")
            if idx_str is not None:
                try:
                    mapa[clave] = int(idx_str)
                except ValueError:
                    pass
        session["csv_mapa"] = mapa

    import csv, io
    reader = csv.reader(io.StringIO(csv_contenido))
    next(reader, [])
    anuncios = set()
    idx_anuncio = mapa.get("anuncio")
    if idx_anuncio is not None:
        for fila in reader:
            if idx_anuncio < len(fila) and fila[idx_anuncio].strip():
                anuncios.add(fila[idx_anuncio].strip())

    if request.method == "POST" and "asignar" in request.form:
        propiedad_map = {}
        for anuncio in anuncios:
            key = f"prop_{anuncio}"
            pid = request.form.get(key)
            if pid:
                propiedad_map[anuncio] = int(pid)

        contenido_bytes = csv_contenido.encode("utf-8")
        filas_ok, omitidas = importador.procesar_csv(contenido_bytes, mapa, propiedad_map)

        importadas = 0
        duplicadas = 0
        for fila in filas_ok:
            try:
                db.execute("""
                    INSERT INTO reservas
                    (propiedad_id,codigo_confirmacion,fecha_inicio,fecha_fin,noches,
                     ingreso_bruto,comision_airbnb,limpieza,ingreso_neto,anticipacion_dias)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    fila["propiedad_id"], fila["codigo_confirmacion"],
                    fila["fecha_inicio"], fila["fecha_fin"], fila["noches"],
                    fila["ingreso_bruto"], fila["comision_airbnb"],
                    fila["limpieza"], fila["ingreso_neto"], fila["anticipacion_dias"]
                ))
                importadas += 1
            except Exception:
                duplicadas += 1

        session.pop("csv_contenido", None)
        session.pop("csv_mapa", None)
        session.pop("csv_encabezados", None)
        session.pop("csv_no_detectadas", None)

        flash(f"Importación completa: {importadas} reservas importadas, "
              f"{duplicadas} duplicadas omitidas, {len(omitidas)} filas con errores.", "ok")
        return render_template("importar.html",
            propiedades=propiedades, paso=4,
            importadas=importadas, duplicadas=duplicadas, omitidas=omitidas)

    return render_template("importar.html",
        propiedades=propiedades, paso=3,
        anuncios=sorted(anuncios), mapa=mapa)


# ════════════════════════════════════════════════════════════════════════════
# COMPETENCIA
# ════════════════════════════════════════════════════════════════════════════

@app.route("/competencia", methods=["GET","POST"])
@login_required
def competencia():
    if request.method == "POST":
        if "csv_comp" in request.files:
            archivo = request.files["csv_comp"]
            import csv, io
            contenido = archivo.read().decode("utf-8-sig", errors="replace")
            reader = csv.DictReader(io.StringIO(contenido))
            count = 0
            for row in reader:
                try:
                    db.execute("""
                        INSERT INTO competencia (barrio,tipo,ambientes,capacidad,precio_noche,fecha,fuente,notas)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (
                        row.get("barrio",""), row.get("tipo",""),
                        row.get("ambientes") or None, row.get("capacidad") or None,
                        float(row.get("precio_noche",0) or 0),
                        row.get("fecha",""), row.get("fuente",""), row.get("notas","")
                    ))
                    count += 1
                except Exception:
                    pass
            flash(f"{count} registros de competencia importados.", "ok")
        else:
            f = request.form
            db.execute("""
                INSERT INTO competencia (barrio,tipo,ambientes,capacidad,precio_noche,fecha,fuente,notas)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                f.get("barrio"), f.get("tipo"),
                f.get("ambientes") or None, f.get("capacidad") or None,
                float(f.get("precio_noche",0) or 0),
                f.get("fecha"), f.get("fuente",""), f.get("notas","")
            ))
            flash("Precio de competencia cargado.", "ok")
        return redirect(url_for("competencia"))

    registros = db.query("SELECT * FROM competencia ORDER BY fecha DESC")
    return render_template("competencia.html", registros=registros)


@app.route("/competencia/<int:cid>/eliminar", methods=["POST"])
@login_required
def eliminar_competencia(cid):
    db.execute("DELETE FROM competencia WHERE id=%s", (cid,))
    flash("Registro eliminado.", "ok")
    return redirect(url_for("competencia"))


# ════════════════════════════════════════════════════════════════════════════
# PRECIOS SUGERIDOS (ruta legacy — mantiene compatibilidad)
# ════════════════════════════════════════════════════════════════════════════

@app.route("/precios", methods=["GET","POST"])
@login_required
def precios():
    propiedades = db.query("SELECT * FROM propiedades ORDER BY nombre")
    resultado   = None
    prop_sel    = None

    if request.method == "POST":
        pid         = int(request.form.get("propiedad_id",0))
        fecha_desde = request.form.get("fecha_desde", date.today().isoformat())
        fecha_hasta = request.form.get("fecha_hasta", date.today().isoformat())

        prop_sel = db.query_one("SELECT * FROM propiedades WHERE id=%s", (pid,))
        if prop_sel:
            reservas_hist = db.query("SELECT * FROM reservas WHERE propiedad_id=%s", (pid,))
            comp_barrio   = db.query(
                "SELECT * FROM competencia WHERE barrio=%s AND tipo=%s",
                (prop_sel.get("barrio",""), prop_sel.get("tipo",""))
            )
            resultado = prec.calcular_precio_sugerido(
                prop_sel, reservas_hist, comp_barrio, fecha_desde, fecha_hasta
            )
            try:
                resultado["justificacion"] = ia.generar_informe(
                    {**resultado["detalle"],
                     "precio_minimo": resultado["precio_minimo"],
                     "precio_sugerido": resultado["precio_sugerido"],
                     "precio_maximo": resultado["precio_maximo"]},
                    nombre_propiedad=prop_sel.get("nombre"),
                    periodo=f"{fecha_desde} al {fecha_hasta}"
                )
            except Exception as e:
                resultado["justificacion"] = f"(No se pudo generar justificación con IA: {e})"
        else:
            flash("Seleccioná una propiedad válida.", "error")

    return render_template("precios.html",
        propiedades=propiedades, resultado=resultado, prop_sel=prop_sel)


# ════════════════════════════════════════════════════════════════════════════
# ASISTENTE DE HUÉSPEDES (legacy — mantiene compatibilidad)
# ════════════════════════════════════════════════════════════════════════════

@app.route("/asistente", methods=["GET","POST"])
@login_required
def asistente():
    propiedades = db.query("SELECT id, nombre, info_huespedes FROM propiedades ORDER BY nombre")
    respuesta   = None
    pendiente   = False
    consulta_guardada = None

    if request.method == "POST":
        pid     = int(request.form.get("propiedad_id",0))
        mensaje = request.form.get("mensaje","").strip()

        if not mensaje:
            flash("Escribí la consulta del huésped.", "error")
        else:
            prop = db.query_one("SELECT * FROM propiedades WHERE id=%s", (pid,))
            if prop:
                try:
                    respuesta, pendiente = ia.responder_huesped(
                        pid, mensaje,
                        prop.get("info_huespedes",""),
                        prop.get("nombre","la propiedad")
                    )
                    cid = db.execute("""
                        INSERT INTO consultas_huespedes
                        (propiedad_id, mensaje, respuesta, pendiente)
                        VALUES (%s,%s,%s,%s)
                        RETURNING id
                    """, (pid, mensaje, respuesta, int(pendiente)))
                    consulta_guardada = cid
                except Exception as e:
                    flash(f"Error al generar respuesta: {e}", "error")
            else:
                flash("Seleccioná una propiedad.", "error")

    historial = db.query("""
        SELECT c.*, p.nombre as prop_nombre
        FROM consultas_huespedes c
        LEFT JOIN propiedades p ON c.propiedad_id = p.id
        ORDER BY c.creada_en DESC LIMIT 50
    """)

    return render_template("asistente.html",
        propiedades=propiedades, respuesta=respuesta,
        pendiente=pendiente, historial=historial)


# ════════════════════════════════════════════════════════════════════════════
# INFORMES
# ════════════════════════════════════════════════════════════════════════════

@app.route("/informes")
@login_required
def informes():
    lista = db.query("SELECT id, titulo, fecha_desde, fecha_hasta, creado_en FROM informes ORDER BY creado_en DESC")
    return render_template("informes.html", informes=lista)


@app.route("/informes/<int:iid>")
@login_required
def ver_informe(iid):
    informe = db.query_one("SELECT * FROM informes WHERE id=%s", (iid,))
    if not informe:
        flash("Informe no encontrado.", "error")
        return redirect(url_for("informes"))
    return render_template("informes.html", informe=informe, informes=[])


@app.route("/informes/generar", methods=["POST"])
@login_required
def generar_informe():
    desde    = request.form.get("desde", date(date.today().year, 1, 1).isoformat())
    hasta    = request.form.get("hasta", date.today().isoformat())
    prop_id  = request.form.get("propiedad_id", None, type=int)

    reservas = db.query("SELECT * FROM reservas")
    filtradas = met.filtrar_reservas(reservas, desde, hasta, prop_id)

    prop = None
    costos_mes = 0
    if prop_id:
        prop = db.query_one("SELECT * FROM propiedades WHERE id=%s", (prop_id,))
        if prop:
            costos_mes = sum([prop.get(k,0) or 0 for k in
                ["costo_expensas","costo_servicios","costo_limpieza","costo_comision"]])

    stats = met.calcular_metricas(filtradas, desde, hasta, costos_mes)

    try:
        comparativas = met.comparar_periodos(reservas, desde, hasta)
        stats_full = {**stats, **comparativas}
    except Exception:
        stats_full = stats

    try:
        texto = ia.generar_informe(
            stats_full,
            nombre_propiedad=prop.get("nombre") if prop else None,
            periodo=f"{desde} al {hasta}"
        )
    except Exception as e:
        flash(f"Error al generar informe con IA: {e}", "error")
        return redirect(url_for("dashboard"))

    titulo = f"Informe {'- ' + prop['nombre'] if prop else 'General'} ({desde} al {hasta})"
    iid = db.execute("""
        INSERT INTO informes (titulo, fecha_desde, fecha_hasta, propiedad_id, contenido)
        VALUES (%s,%s,%s,%s,%s)
        RETURNING id
    """, (titulo, desde, hasta, prop_id, texto))

    flash("Informe generado y guardado.", "ok")
    return redirect(url_for("ver_informe", iid=iid))


@app.route("/informes/<int:iid>/eliminar", methods=["POST"])
@login_required
def eliminar_informe(iid):
    db.execute("DELETE FROM informes WHERE id=%s", (iid,))
    flash("Informe eliminado.", "ok")
    return redirect(url_for("informes"))


# ════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
