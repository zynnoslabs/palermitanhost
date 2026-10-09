# app.py
import os
import time
# ### CAMBIO AQUÍ ### — el servidor de Render usa hora UTC: de 21 a 24 h ya era "mañana".
# Con esto date.today() y datetime.now() dan la hora de Buenos Aires en todo el sistema.
os.environ["TZ"] = "America/Argentina/Buenos_Aires"
if hasattr(time, "tzset"):
    time.tzset()
import json
from datetime import datetime, date, timedelta   # ### CAMBIO AQUÍ ###
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
import competencia_ia   # ### CAMBIO AQUÍ ###
import monedas         # ### CAMBIO AQUÍ ###
import competencia_auto  # ### CAMBIO AQUÍ ###
import hmac
import ayuda   # ### CAMBIO AQUÍ ### textos del ícono 'i'
import privacidad   # ### CAMBIO AQUÍ ### nombres de huéspedes ocultos para la IA
import archivo_anual   # ### CAMBIO AQUÍ ### archivo anual descargable

from werkzeug.middleware.proxy_fix import ProxyFix   # ### CAMBIO AQUÍ ###

app = Flask(__name__)
app.jinja_env.globals["info"] = ayuda.info   # ### CAMBIO AQUÍ ### {{ info('clave') }} en las plantillas

# ### CAMBIO AQUÍ ### — SEGURIDAD: sin contraseña ni clave secreta propias, el sistema NO arranca.
# Antes, si faltaban, entraba cualquiera con admin / admin123.
def _variable_obligatoria(nombre, largo_minimo):
    valor = os.getenv(nombre) or ""
    if len(valor) < largo_minimo or valor in ("admin123", "cambiar-esto-en-produccion", "cambiar-esto"):
        raise RuntimeError(
            f"Falta configurar {nombre} (mínimo {largo_minimo} caracteres) en las variables de entorno "
            f"de Render o en el archivo .env. Por seguridad el sistema no arranca sin esto.")
    return valor

app.secret_key = _variable_obligatoria("SECRET_KEY", 16)
ADMIN_USER = _variable_obligatoria("ADMIN_USER", 3)
ADMIN_PASS = _variable_obligatoria("ADMIN_PASS", 10)

# ### CAMBIO AQUÍ ### — cookie de sesión segura: solo por https (en Render), no la lee JavaScript,
# no viaja en pedidos desde otras páginas y vence a las 12 horas.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.getenv("RENDER")),   # Render define RENDER=true; en tu compu (http) no
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)
# Render está detrás de un proxy: así se ve la IP real del visitante (para el bloqueo de login)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

MAX_FALLOS_LOGIN = 5
MINUTOS_BLOQUEO = 15

# ── Blueprints ───────────────────────────────────────────────────────────────
from asistente_route import asistente_bp, _cargar_historial   # ### CAMBIO AQUÍ ###
from exportar_routes import exportar_bp
from ruta_precios    import precios_bp

app.register_blueprint(asistente_bp)
app.register_blueprint(exportar_bp)
# app.register_blueprint(precios_bp)   # ### CAMBIO AQUÍ ### desactivado: scrapeaba Airbnb y tenía precios fijos de Palermo (la app usa /precios)

# ### CAMBIO AQUÍ ### — PostgreSQL devuelve fechas como datetime; antes {{ x[:10] }} rompía la página
@app.template_filter("fecha")
def filtro_fecha(valor, largo=10):
    # ### CAMBIO AQUÍ ### — fechas en formato argentino: 05/10/2026 (antes 2026-10-05)
    if not valor:
        return ""
    if not hasattr(valor, "strftime"):
        txt = str(valor).replace("T", " ")
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                valor = datetime.strptime(txt[:16] if "%H" in fmt else txt[:10], fmt)
                break
            except ValueError:
                continue
        else:
            return str(valor)[:largo]
    if largo > 10 and isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y %H:%M")
    return valor.strftime("%d/%m/%Y")


@app.template_filter("num")
def filtro_num(valor, decimales=1):
    # ### CAMBIO AQUÍ ### — números con coma decimal: 70,8 (antes 70.8)
    if valor is None or valor == "":
        return "—"
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    txt = f"{v:,.{decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if decimales and txt.endswith("," + "0" * decimales):
        txt = txt[: -(decimales + 1)]
    return txt


def _costos_y_unidades(prop_id, vista="ARS", tc=None):
    """Costos fijos mensuales (en la moneda 'vista') y cantidad de unidades."""
    props = (db.query("SELECT * FROM propiedades WHERE id=%s", (prop_id,)) if prop_id
             else db.query("SELECT * FROM propiedades"))
    return monedas.costos_mensuales(props, vista, tc), max(len(props), 1)


# ### CAMBIO AQUÍ ### — moneda en pantalla (ARS o USD) y tipo de cambio disponibles en todas las páginas
def moneda_vista():
    return session.get("moneda_vista", "ARS")


@app.context_processor
def inyectar_monedas():
    try:
        tc = monedas.get_tc()
    except Exception:
        tc = None
    return {"vista": moneda_vista(), "tc_info": tc, "tipos_dolar": monedas.TIPOS_DOLAR}


@app.template_filter("dinero")
def filtro_dinero(monto, moneda="ARS", convertir_a=None):
    """{{ monto|dinero('USD') }} muestra en esa moneda; con convertir_a='vista' pasa a la moneda elegida."""
    destino = moneda_vista() if convertir_a == "vista" else (convertir_a or moneda or "ARS")
    v = monedas.convertir(monto or 0, moneda or "ARS", destino, monedas.tc_valor() if destino != moneda else None)
    if v is None:   # sin tipo de cambio: se muestra en la moneda original
        return monedas.formatear(monto or 0, moneda or "ARS")
    return monedas.formatear(v, destino)


@app.route("/moneda/<m>")
def cambiar_moneda(m):
    if m in monedas.MONEDAS:
        session["moneda_vista"] = m
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/tipo-cambio", methods=["POST"])
def tipo_cambio():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    try:
        if request.form.get("tipo"):
            data = monedas.traer_tc(request.form["tipo"])
            flash(f"Tipo de cambio actualizado: {data['tipo']} = $ {data['valor']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), "ok")
        else:
            valor = importador.parsear_monto(request.form.get("valor"))
            if valor <= 0:
                raise ValueError("valor inválido")
            monedas.guardar_tc(valor, "manual")
            flash("Tipo de cambio guardado.", "ok")
    except Exception as e:
        flash(f"No se pudo actualizar el tipo de cambio: {e}", "error")
    return redirect(request.referrer or url_for("dashboard"))


# ### CAMBIO AQUÍ ### alias de huéspedes ("Huésped #12") para no mandar nombres reales a la IA
def _alias_huespedes(extra=None):
    filas = db.query("""
        SELECT TRIM(huesped_nombre) AS n, MIN(id) AS i FROM reservas
        WHERE COALESCE(TRIM(huesped_nombre),'') <> '' GROUP BY TRIM(huesped_nombre)
    """)
    alias = privacidad.armar_alias([(f["n"], f["i"]) for f in filas])
    if extra and extra.strip() and extra.strip() not in alias:
        alias[extra.strip()] = "Huésped #0"
    return alias


# ### CAMBIO AQUÍ ### — SEGURIDAD XSS: solo se guardan links http/https
def _link_seguro(url):
    url = (url or "").strip()
    return url[:500] if url.lower().startswith(("http://", "https://")) else ""


# ### CAMBIO AQUÍ ### — SEGURIDAD: encabezados en todas las respuestas.
# CSP: el navegador solo carga scripts de este sitio y de cdnjs (Chart.js), y solo se conecta a este sitio.
# Aunque alguien lograra meter código, no podría mandar datos a otro servidor ni cargar scripts externos.
CSP = ("default-src 'self'; "
       "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
       "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src 'self' https://fonts.gstatic.com data:; "
       "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
       "base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


@app.after_request
def encabezados_seguridad(resp):
    resp.headers.setdefault("Content-Security-Policy", CSP)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if os.getenv("RENDER"):
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return resp


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

# ### CAMBIO AQUÍ ### — bloqueo después de 5 intentos fallidos (15 minutos)
def _minutos_bloqueado(ip):
    row = db.query_one("""
        SELECT CEIL(EXTRACT(EPOCH FROM (bloqueado_hasta - NOW())) / 60) AS m
        FROM login_intentos WHERE ip=%s AND bloqueado_hasta > NOW()
    """, (ip,))
    return int(row["m"]) if row and row["m"] else 0


def _registrar_fallo(ip):
    # Los fallos de hace más de 15 minutos no cuentan (se reinicia el contador)
    db.execute("""
        INSERT INTO login_intentos (ip, fallos, ultimo_fallo) VALUES (%s, 1, NOW())
        ON CONFLICT (ip) DO UPDATE SET
          fallos = CASE WHEN login_intentos.ultimo_fallo < NOW() - INTERVAL '15 minutes'
                        THEN 1 ELSE login_intentos.fallos + 1 END,
          ultimo_fallo = NOW()
    """, (ip,))
    db.execute("""
        UPDATE login_intentos SET bloqueado_hasta = NOW() + (%s * INTERVAL '1 minute'), fallos = 0
        WHERE ip=%s AND fallos >= %s
    """, (MINUTOS_BLOQUEO, ip, MAX_FALLOS_LOGIN))


@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        ip = request.remote_addr or "desconocida"
        espera = _minutos_bloqueado(ip)
        if espera:
            flash(f"Demasiados intentos fallidos. Probá de nuevo en {espera} minuto(s).", "error")
            return render_template("login.html"), 429
        usuario_ok = hmac.compare_digest((request.form.get("usuario") or "").encode(), ADMIN_USER.encode())
        clave_ok = hmac.compare_digest((request.form.get("password") or "").encode(), ADMIN_PASS.encode())
        if usuario_ok and clave_ok:
            db.execute("DELETE FROM login_intentos WHERE ip=%s", (ip,))
            session.clear()
            session["logged_in"] = True
            session.permanent = True   # vence a las 12 horas
            return redirect(url_for("dashboard"))
        _registrar_fallo(ip)
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

    # ### CAMBIO AQUÍ ### — los montos se pasan a la moneda elegida (ARS o USD)
    vista, tc = moneda_vista(), monedas.tc_valor()
    reservas = db.query("SELECT * FROM reservas")
    reservas_filtradas = met.filtrar_reservas(reservas, desde, hasta, prop_id)
    reservas_filtradas, sin_tc = monedas.convertir_reservas(reservas_filtradas, vista, tc)
    if sin_tc:
        flash(f"{sin_tc} reservas están en otra moneda y no se sumaron: cargá el tipo de cambio "
              f"(arriba a la derecha).", "warn")

    costos_mes, unidades = _costos_y_unidades(prop_id, vista, tc)
    stats = met.calcular_metricas(reservas_filtradas, desde, hasta, costos_mes, unidades)
    por_mes = met.metricas_por_mes(reservas_filtradas, prop_id)

    informes = db.query("SELECT id, titulo, creado_en FROM informes ORDER BY creado_en DESC LIMIT 5")

    # ### CAMBIO AQUÍ ### — próximas reservas, reseñas pendientes y ocupación de los últimos 7 días
    hoy = date.today()
    proximas = db.query("""
        SELECT r.*, p.nombre AS prop_nombre FROM reservas r
        LEFT JOIN propiedades p ON p.id = r.propiedad_id
        WHERE r.fecha_inicio >= %s AND COALESCE(r.estado,'') <> 'cancelada'
          AND (%s::int IS NULL OR r.propiedad_id = %s::int)
        ORDER BY r.fecha_inicio LIMIT 8
    """, (hoy.isoformat(), prop_id, prop_id))
    resenas_pend = db.query_one("""
        SELECT COUNT(*) AS n FROM resenas
        WHERE pendiente = 1 AND (%s::int IS NULL OR propiedad_id = %s::int)
    """, (prop_id, prop_id))["n"]
    unidades_activas = len([p for p in propiedades
                            if (not prop_id or p["id"] == prop_id) and p.get("estado") != "inactiva"]) or 1
    ocup_7 = met.ocupacion_diaria(
        [r for r in reservas if r.get("estado") != "cancelada" and (not prop_id or r.get("propiedad_id") == prop_id)],
        hoy - timedelta(days=6), hoy, unidades_activas)

    return render_template("dashboard.html",
        propiedades=propiedades, stats=stats, por_mes=por_mes,   # ### CAMBIO AQUÍ ### se escapa con |tojson
        alerta_comp=competencia_auto.alerta_sin_datos(),   # ### CAMBIO AQUÍ ### aviso si la competencia no se actualiza
        archivo_pendiente=archivo_anual.anio_pendiente(),   # ### CAMBIO AQUÍ ### aviso del archivo anual
        desde=desde, hasta=hasta, prop_id=prop_id, informes=informes,
        proximas=proximas, resenas_pend=resenas_pend, ocup_7=ocup_7)


# ════════════════════════════════════════════════════════════════════════════
# PROPIEDADES
# ════════════════════════════════════════════════════════════════════════════

@app.route("/propiedades")
@login_required
def propiedades():
    props = db.query("SELECT * FROM propiedades ORDER BY nombre")
    # ### CAMBIO AQUÍ ### — lista de huéspedes de la propiedad elegida
    ver = request.args.get("ver", type=int) or (props[0]["id"] if props else None)
    huespedes = db.query("""
        SELECT * FROM reservas WHERE propiedad_id=%s
        ORDER BY fecha_inicio DESC LIMIT 30
    """, (ver,)) if ver else []
    return render_template("propiedades.html", propiedades=props, ver=ver, huespedes=huespedes)


@app.route("/propiedades/nueva", methods=["GET","POST"])
@login_required
def nueva_propiedad():
    if request.method == "POST":
        f = request.form
        db.execute("""
            INSERT INTO propiedades
            (nombre,direccion,barrio,tipo,ambientes,capacidad,precio_base,
             costo_expensas,costo_servicios,costo_limpieza,costo_comision,info_huespedes,estado,
             rating,reviews_count,moneda,ciudad)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            f.get("nombre"), f.get("direccion"), f.get("barrio"), f.get("tipo"),
            f.get("ambientes") or None, f.get("capacidad") or None,
            f.get("precio_base") or 0,
            f.get("costo_expensas") or 0, f.get("costo_servicios") or 0,
            f.get("costo_limpieza") or 0, f.get("costo_comision") or 0,
            f.get("info_huespedes",""), f.get("estado","activa"),   # ### CAMBIO AQUÍ ###
            f.get("rating") or None, f.get("reviews_count") or 0, f.get("moneda","ARS"),
            (f.get("ciudad") or "").strip() or "Buenos Aires"   # ### CAMBIO AQUÍ ###
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
            costo_limpieza=%s,costo_comision=%s,info_huespedes=%s,estado=%s,
            rating=%s,reviews_count=%s,moneda=%s,ciudad=%s
            WHERE id=%s
        """, (
            f.get("nombre"), f.get("direccion"), f.get("barrio"), f.get("tipo"),
            f.get("ambientes") or None, f.get("capacidad") or None,
            f.get("precio_base") or 0,
            f.get("costo_expensas") or 0, f.get("costo_servicios") or 0,
            f.get("costo_limpieza") or 0, f.get("costo_comision") or 0,
            f.get("info_huespedes",""), f.get("estado","activa"),   # ### CAMBIO AQUÍ ###
            f.get("rating") or None, f.get("reviews_count") or 0, f.get("moneda","ARS"),
            (f.get("ciudad") or "").strip() or "Buenos Aires", pid   # ### CAMBIO AQUÍ ###
        ))
        flash("Propiedad actualizada.", "ok")
        return redirect(url_for("propiedades"))
    return render_template("propiedad_form.html", prop=prop)


@app.route("/propiedades/<int:pid>/eliminar", methods=["POST"])
@login_required
def eliminar_propiedad(pid):
    # ### CAMBIO AQUÍ ### — antes daba error 500 si la propiedad tenía reservas o consultas
    usos = db.query_one("""
        SELECT (SELECT COUNT(*) FROM reservas WHERE propiedad_id=%s) +
               (SELECT COUNT(*) FROM consultas_huespedes WHERE propiedad_id=%s) +
               (SELECT COUNT(*) FROM resenas WHERE propiedad_id=%s) AS n
    """, (pid, pid, pid))
    if usos and usos["n"]:
        flash("No se puede eliminar: la propiedad tiene reservas o consultas cargadas. "
              "Podés editarla y cambiarle el nombre o los datos.", "error")
        return redirect(url_for("propiedades"))
    db.execute("DELETE FROM competencia WHERE propiedad_id=%s", (pid,))
    db.execute("DELETE FROM propiedades WHERE id=%s", (pid,))
    flash("Propiedad eliminada.", "ok")
    return redirect(url_for("propiedades"))


# ════════════════════════════════════════════════════════════════════════════
# IMPORTAR CSV
# ════════════════════════════════════════════════════════════════════════════

def _guardar_csv_pendiente(texto):
    db.execute("""
        INSERT INTO config (clave, valor) VALUES ('csv_pendiente', %s)
        ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor
    """, (texto,))


def _leer_csv_pendiente():
    row = db.query_one("SELECT valor FROM config WHERE clave='csv_pendiente'")
    return row["valor"] if row and row["valor"] else ""


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

        # ### CAMBIO AQUÍ ### — el CSV se guarda en la base, no en la cookie
        # (la cookie tiene límite de 4 KB: con un CSV real se perdía y cerraba la sesión)
        _guardar_csv_pendiente(contenido.decode("utf-8-sig", errors="replace"))
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
    csv_contenido   = _leer_csv_pendiente()   # ### CAMBIO AQUÍ ###
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
        # ### CAMBIO AQUÍ ### — si el CSV no trae moneda, se usa la de la propiedad
        mon_prop = {p["id"]: (p.get("moneda") or "ARS") for p in db.query("SELECT id, moneda FROM propiedades")}
        for fila in filas_ok:
            fila["moneda"] = fila.get("moneda") or mon_prop.get(fila["propiedad_id"], "ARS")

        # ### CAMBIO AQUÍ ### — si la reserva ya existe se ACTUALIZA (estado, huésped, montos)
        # en vez de descartarla. Así se puede importar el export de Reservas (futuras)
        # y después el de Ganancias sin duplicar.
        importadas = 0
        duplicadas = 0
        # ### CAMBIO AQUÍ ### qué export es: "Ganancias" (montos exactos) o "Reservas" (monto aproximado)
        solo_completar = importador.tipo_de_archivo(csv_encabezados) == "reservas"
        for fila in filas_ok:
            try:
                nueva = db.execute("""
                    INSERT INTO reservas
                    (propiedad_id,codigo_confirmacion,fecha_inicio,fecha_fin,noches,
                     ingreso_bruto,comision_airbnb,limpieza,ingreso_neto,anticipacion_dias,
                     huesped_nombre,estado,moneda)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (codigo_confirmacion) DO UPDATE SET
                      huesped_nombre = COALESCE(NULLIF(EXCLUDED.huesped_nombre,''), reservas.huesped_nombre),
                      estado = CASE WHEN EXCLUDED.estado = 'completada' AND reservas.estado = 'cancelada'
                                    THEN reservas.estado ELSE EXCLUDED.estado END,
                      -- ### CAMBIO AQUÍ ### el archivo de "Reservas" no pisa los montos que ya vinieron del de Ganancias
                      ingreso_bruto   = CASE WHEN %s AND reservas.ingreso_bruto <> 0 THEN reservas.ingreso_bruto
                                             WHEN EXCLUDED.ingreso_bruto  > 0 THEN EXCLUDED.ingreso_bruto  ELSE reservas.ingreso_bruto END,
                      comision_airbnb = CASE WHEN %s AND reservas.comision_airbnb <> 0 THEN reservas.comision_airbnb
                                             WHEN EXCLUDED.comision_airbnb <> 0 THEN EXCLUDED.comision_airbnb ELSE reservas.comision_airbnb END,
                      limpieza        = CASE WHEN %s AND reservas.limpieza <> 0 THEN reservas.limpieza
                                             WHEN EXCLUDED.limpieza       > 0 THEN EXCLUDED.limpieza       ELSE reservas.limpieza END,
                      ingreso_neto    = CASE WHEN %s AND reservas.ingreso_neto <> 0 THEN reservas.ingreso_neto
                                             WHEN EXCLUDED.ingreso_neto   > 0 THEN EXCLUDED.ingreso_neto   ELSE reservas.ingreso_neto END,
                      anticipacion_dias = COALESCE(EXCLUDED.anticipacion_dias, reservas.anticipacion_dias),
                      propiedad_id = EXCLUDED.propiedad_id,
                      fecha_inicio = EXCLUDED.fecha_inicio,
                      fecha_fin    = COALESCE(EXCLUDED.fecha_fin, reservas.fecha_fin),
                      noches       = CASE WHEN EXCLUDED.noches > 0 THEN EXCLUDED.noches ELSE reservas.noches END,
                      moneda = EXCLUDED.moneda
                    RETURNING (xmax = 0)
                """, (
                    fila["propiedad_id"], fila["codigo_confirmacion"],
                    fila["fecha_inicio"], fila["fecha_fin"], fila["noches"],
                    fila["ingreso_bruto"], fila["comision_airbnb"],
                    fila["limpieza"], fila["ingreso_neto"], fila["anticipacion_dias"],
                    fila.get("huesped_nombre", ""), fila.get("estado", "completada"), fila["moneda"],
                    solo_completar, solo_completar, solo_completar, solo_completar
                ))
                if nueva:
                    importadas += 1
                else:
                    duplicadas += 1
            except Exception:
                omitidas.append({"fila": "—", "motivo": f"No se pudo guardar {fila['codigo_confirmacion']}"})

        _guardar_csv_pendiente("")   # ### CAMBIO AQUÍ ###
        session.pop("csv_mapa", None)
        session.pop("csv_encabezados", None)
        session.pop("csv_no_detectadas", None)

        flash(f"Importación completa: {importadas} reservas nuevas, "
              f"{duplicadas} ya existían (actualizadas), {len(omitidas)} filas con errores.", "ok")
        return render_template("importar.html",
            propiedades=propiedades, paso=4,
            importadas=importadas, duplicadas=duplicadas, omitidas=omitidas)

    return render_template("importar.html",
        propiedades=propiedades, paso=3,
        anuncios=sorted(anuncios), mapa=mapa)


# ════════════════════════════════════════════════════════════════════════════
# COMPETENCIA
# ════════════════════════════════════════════════════════════════════════════

# ### CAMBIO AQUÍ ### — Competencia: búsqueda automática con IA (sin CSV).
# La carga manual queda como opción secundaria por si la IA no encuentra nada.
@app.route("/competencia", methods=["GET","POST"])
@login_required
def competencia():
    if request.method == "POST":
        f = request.form
        db.execute("""
            INSERT INTO competencia (barrio,tipo,ambientes,capacidad,precio_noche,fecha,fuente,notas,
                                     link,zona,origen,moneda,propiedad_id,plataforma,titulo)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'manual',%s,%s,%s,%s)
        """, (
            f.get("barrio"), f.get("tipo"),
            f.get("ambientes") or None, f.get("capacidad") or None,
            float(f.get("precio_noche",0) or 0),
            f.get("fecha") or date.today().isoformat(), f.get("fuente",""), f.get("notas",""),
            _link_seguro(f.get("link","")), f.get("zona",""), f.get("moneda","ARS"),   # ### CAMBIO AQUÍ ### link validado
            request.args.get("pid", type=int),   # ### CAMBIO AQUÍ ### queda asociado a la propiedad
            f.get("plataforma") or "Manual", f.get("titulo","")
        ))
        flash("Competidor cargado. Ya cuenta para el precio de referencia de la zona.", "ok")
        return redirect(url_for("competencia", pid=request.args.get("pid")))

    propiedades = db.query("SELECT * FROM propiedades ORDER BY nombre")
    pid = request.args.get("pid", type=int)
    if not pid and propiedades:
        pid = propiedades[0]["id"]
    prop_sel = next((p for p in propiedades if p["id"] == pid), None)

    registros, resumen, stats = [], None, None
    if prop_sel:
        # ### CAMBIO AQUÍ ### solo los vigentes: IA de los últimos 30 días + cargados a mano
        registros = competencia_auto.comparables_vigentes(pid, prop_sel.get("barrio"))
        row = db.query_one("SELECT valor FROM config WHERE clave=%s",
                           (f"competencia_resumen_{pid}",))
        if row:
            try:
                resumen = json.loads(row["valor"])
            except Exception:
                resumen = None
        stats = competencia_ia.calcular_stats(registros, prop_sel.get("moneda") or "ARS",
                                              monedas.tc_valor())   # ### CAMBIO AQUÍ ###

    hist = competencia_auto.historial(pid) if prop_sel else []   # ### CAMBIO AQUÍ ###
    return render_template("competencia.html", propiedades=propiedades,
                           prop_sel=prop_sel, registros=registros,
                           resumen=resumen, stats=stats, historial=hist,
                           n_ia=sum(1 for r in registros if r.get("origen") == "ia"),   # ### CAMBIO AQUÍ ###
                           n_manual=sum(1 for r in registros if r.get("origen") != "ia"),
                           dias_vigencia=competencia_auto.DIAS_VIGENCIA,
                           historial_json=list(reversed(hist)),   # ### CAMBIO AQUÍ ### |tojson
                           corrida=competencia_auto.ultima_corrida(),
                           auto_activa=bool(os.getenv("TAREAS_TOKEN")),
                           tavily_activo=bool(os.getenv("TAVILY_API_KEY")),
                           motores=[m for m, k in (("Google (SerpApi)", "SERPAPI_API_KEY"), ("Tavily", "TAVILY_API_KEY"))
                                    if os.getenv(k)] + (["Groq"] if os.getenv("COMPETENCIA_RESPALDO_GROQ") == "1" else []))   # ### CAMBIO AQUÍ ###


@app.route("/competencia/buscar", methods=["POST"])
@login_required
def buscar_competencia():
    pid = request.form.get("propiedad_id", type=int)
    prop = db.query_one("SELECT * FROM propiedades WHERE id=%s", (pid,)) if pid else None
    if not prop:
        flash("Elegí una propiedad para buscar su competencia.", "error")
        return redirect(url_for("competencia"))

    res = competencia_ia.buscar_comparables(prop, monedas.tc_valor())   # ### CAMBIO AQUÍ ###
    if not res["ok"]:
        flash(res["error"], "error")
        return redirect(url_for("competencia", pid=pid))

    # ### CAMBIO AQUÍ ### — guarda anuncios + resumen + foto del día (historial)
    competencia_auto.guardar_resultado(prop, res, monedas.tc_valor())
    gasto = (f" · {res['creditos_tavily']} crédito(s) de Tavily" if res.get("creditos_tavily") else "")
    flash(f"Se encontraron {len(res['comparables'])} propiedades similares (fuente: {res.get('fuente')}{gasto}).", "ok")
    return redirect(url_for("competencia", pid=pid))


# ### CAMBIO AQUÍ ### — actualización automática nocturna (la llama cron-job.org con un token secreto)
@app.route("/tareas/competencia", methods=["GET", "POST"])
def tarea_competencia():
    token_ok = os.getenv("TAREAS_TOKEN")
    # ### CAMBIO AQUÍ ### — preferí mandarlo como encabezado X-Token (no queda en los registros);
    # ?token= se sigue aceptando para no romper una tarea ya configurada.
    token = request.headers.get("X-Token") or request.args.get("token") or ""
    if not token_ok or not hmac.compare_digest(token, token_ok):
        return jsonify({"ok": False, "error": "No autorizado"}), 403
    competencia_auto.correr_en_segundo_plano()
    return jsonify({"ok": True, "mensaje": "Actualización de competencia iniciada."})


@app.route("/salud")
def salud():
    """Para 'despertar' el servidor de Render antes de la tarea nocturna."""
    return "ok"


@app.route("/competencia/<int:cid>/eliminar", methods=["POST"])
@login_required
def eliminar_competencia(cid):
    db.execute("DELETE FROM competencia WHERE id=%s", (cid,))
    flash("Registro eliminado.", "ok")
    return redirect(url_for("competencia", pid=request.args.get("pid")))  # ### CAMBIO AQUÍ ###


# ════════════════════════════════════════════════════════════════════════════
# PRECIOS SUGERIDOS (ruta legacy — mantiene compatibilidad)
# ════════════════════════════════════════════════════════════════════════════

@app.route("/precios", methods=["GET","POST"])
@login_required
def precios():
    # ### CAMBIO AQUÍ ### — precio estratégico (igual que el demo): mediana de la competencia
    # encontrada por la IA, ajustada por puntaje, reseñas, temporada, ocupación y fin de semana.
    import statistics
    from precio_estrategico import calcular_precio_estrategico

    propiedades = db.query("SELECT * FROM propiedades ORDER BY nombre")
    pid = request.values.get("propiedad_id", type=int) or (propiedades[0]["id"] if propiedades else None)
    prop_sel = next((p for p in propiedades if p["id"] == pid), None)
    fecha = request.values.get("fecha", date.today().isoformat())
    resultado, mercado = None, None

    if prop_sel:
        comps = competencia_auto.comparables_vigentes(pid, prop_sel.get("barrio"))   # ### CAMBIO AQUÍ ###
        # ### CAMBIO AQUÍ ### — todo en la moneda de la propiedad (convierte con el tipo de cambio)
        st = competencia_ia.calcular_stats(comps, prop_sel.get("moneda") or "ARS", monedas.tc_valor()) if comps else None
        if st:
            mercado = {
                "mediana": st["mediana"], "min": st["minimo"], "max": st["maximo"],
                "rating_promedio_zona": st["rating"] or 4.5,   # 4.5 solo para el cálculo
                "rating_real": bool(st["rating"]),        # ### CAMBIO AQUÍ ### en pantalla "—" si no hay puntajes
                "cantidad_propiedades": st["cantidad"],
                "sin_convertir": st["sin_convertir"],
                "simbolo": "US$" if prop_sel.get("moneda") == "USD" else "$",
                "fecha": max((c.get("fecha") or "") for c in comps),
            }

    if request.method == "POST" and prop_sel:
        if not mercado:
            flash("Primero buscá la competencia de esta propiedad en la sección Competencia.", "error")
        else:
            desde_90 = (date.today() - timedelta(days=90)).isoformat()
            reservas_hist = db.query("""
                SELECT * FROM reservas WHERE propiedad_id=%s AND fecha_inicio >= %s
                  AND COALESCE(estado,'') <> 'cancelada'
            """, (pid, desde_90))
            resultado = calcular_precio_estrategico(prop_sel, mercado, reservas_hist, fecha)
            # Piso: nunca por debajo de los costos fijos por noche + 15%
            costos = sum((prop_sel.get(k) or 0) for k in
                         ["costo_expensas", "costo_servicios", "costo_limpieza", "costo_comision"])
            piso = round(costos / 30.44 * 1.15)
            resultado["costo_noche"] = round(costos / 30.44)
            if piso > resultado["precio_minimo"]:
                resultado["precio_minimo"] = piso
                resultado["explicacion"] += (f" El mínimo se subió a {monedas.formatear(piso, prop_sel.get('moneda') or 'ARS')}"
                                             f" para cubrir tus costos fijos.")

    return render_template("precios.html", propiedades=propiedades, prop_sel=prop_sel,
                           resultado=resultado, mercado=mercado, fecha=fecha)


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
                    alias = _alias_huespedes()   # ### CAMBIO AQUÍ ### sin nombres a Groq
                    respuesta, pendiente = ia.responder_huesped(
                        pid, privacidad.ocultar(mensaje, alias)[0],
                        prop.get("info_huespedes",""),
                        prop.get("nombre","la propiedad")
                    )
                    respuesta = privacidad.mostrar(respuesta, alias)
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
    # ### CAMBIO AQUÍ ### — chat de negocio, filtro de consultas y reseñas
    resenas = db.query("""
        SELECT r.*, p.nombre AS prop_nombre FROM resenas r
        LEFT JOIN propiedades p ON p.id = r.propiedad_id
        ORDER BY r.pendiente DESC, r.creada_en DESC LIMIT 50
    """)
    try:
        chat_hist = _cargar_historial()
    except Exception:
        chat_hist = []

    return render_template("asistente.html",
        propiedades=propiedades, respuesta=respuesta,
        pendiente=pendiente, historial=historial,
        resenas=resenas, chat_hist=chat_hist,
        tab="huespedes" if request.method == "POST" else request.args.get("tab", "negocio"))


# ### CAMBIO AQUÍ ### — responder a mano una consulta pendiente
@app.route("/asistente/consulta/<int:cid>/responder", methods=["POST"])
@login_required
def responder_consulta(cid):
    texto = request.form.get("respuesta", "").strip()
    if texto:
        db.execute("UPDATE consultas_huespedes SET respuesta=%s, pendiente=0 WHERE id=%s", (texto, cid))
        flash("Consulta marcada como respondida.", "ok")
    return redirect(url_for("asistente", tab="huespedes"))


# ### CAMBIO AQUÍ ### — reseñas: cargar, generar respuesta con IA, marcar respondida
@app.route("/resenas/nueva", methods=["POST"])
@login_required
def nueva_resena():
    f = request.form
    pid = f.get("propiedad_id", type=int)
    texto = (f.get("texto") or "").strip()
    if not pid or not texto:
        flash("Elegí la propiedad y pegá el texto de la reseña.", "error")
        return redirect(url_for("asistente", tab="resenas"))
    prop = db.query_one("SELECT nombre FROM propiedades WHERE id=%s", (pid,))
    puntaje = f.get("puntaje", type=int)
    try:
        alias = _alias_huespedes(f.get("huesped"))   # ### CAMBIO AQUÍ ### sin nombres a Groq
        borrador = ia.responder_resena(privacidad.ocultar(texto, alias)[0], puntaje,
                                       prop["nombre"] if prop else "la propiedad",
                                       alias.get((f.get("huesped") or "").strip()))
        borrador = privacidad.mostrar(borrador, alias)
    except Exception as e:
        borrador = ""
        flash(f"Reseña guardada, pero no se pudo generar la respuesta con IA: {e}", "error")
    db.execute("""
        INSERT INTO resenas (propiedad_id, huesped, puntaje, texto, respuesta, pendiente, fecha)
        VALUES (%s,%s,%s,%s,%s,1,%s)
    """, (pid, f.get("huesped", ""), puntaje, texto, borrador, date.today().isoformat()))
    return redirect(url_for("asistente", tab="resenas"))


@app.route("/resenas/<int:rid>/responder", methods=["POST"])
@login_required
def responder_resena(rid):
    texto = request.form.get("respuesta", "").strip()
    db.execute("UPDATE resenas SET respuesta=%s, pendiente=0 WHERE id=%s", (texto, rid))
    flash("Reseña marcada como respondida.", "ok")
    return redirect(url_for("asistente", tab="resenas"))


@app.route("/resenas/<int:rid>/eliminar", methods=["POST"])
@login_required
def eliminar_resena(rid):
    db.execute("DELETE FROM resenas WHERE id=%s", (rid,))
    return redirect(url_for("asistente", tab="resenas"))


# ════════════════════════════════════════════════════════════════════════════
# INFORMES
# ════════════════════════════════════════════════════════════════════════════

# ### CAMBIO AQUÍ ### — COPIA DE SEGURIDAD: descarga un .zip con todas las tablas en CSV
# (se abren con Excel). Complementa la copia automática semanal de GitHub.
TABLAS_RESPALDO_EXCLUIDAS = {"login_intentos"}


@app.route("/respaldo/descargar")
@login_required
def descargar_respaldo():
    import io, zipfile
    from flask import send_file
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        archivo_anual.escribir_base_completa(z)   # ### CAMBIO AQUÍ ### misma función que el archivo anual
    buf.seek(0)
    nombre = f"palermitanhost-respaldo-{datetime.now().strftime('%Y-%m-%d')}.zip"
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=nombre)


# ### CAMBIO AQUÍ ### — ARCHIVO ANUAL: datos del año + resumen + base completa + código + LEEME
@app.route("/archivo-anual/<int:anio>")
@login_required
def descargar_archivo_anual(anio):
    from flask import send_file
    if anio not in archivo_anual.anios_con_datos():
        flash(f"No hay reservas cargadas en {anio}.", "error")
        return redirect(url_for("informes"))
    buf = archivo_anual.generar_zip(anio)
    if anio < archivo_anual.hoy().year:   # solo los años terminados apagan el aviso del Dashboard
        archivo_anual.marcar_descargado(anio)
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                     download_name=f"PalermitanHost-Archivo-anual-{anio}.zip")


@app.route("/informes")
@login_required
def informes():
    lista = db.query("SELECT id, titulo, fecha_desde, fecha_hasta, creado_en FROM informes ORDER BY creado_en DESC")
    # ### CAMBIO AQUÍ ### años disponibles para el archivo anual y si ya se descargaron
    anios = [{"anio": a, "descargado": archivo_anual.descargado(a), "en_curso": a >= archivo_anual.hoy().year}
             for a in archivo_anual.anios_con_datos()]
    return render_template("informes.html", informes=lista, anios_archivo=anios)


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

    # ### CAMBIO AQUÍ ### — informe en la moneda elegida
    vista, tc = moneda_vista(), monedas.tc_valor()
    reservas, _ = monedas.convertir_reservas(db.query("SELECT * FROM reservas"), vista, tc)
    filtradas = met.filtrar_reservas(reservas, desde, hasta, prop_id)

    prop = db.query_one("SELECT * FROM propiedades WHERE id=%s", (prop_id,)) if prop_id else None
    costos_mes, unidades = _costos_y_unidades(prop_id, vista, tc)
    stats = met.calcular_metricas(filtradas, desde, hasta, costos_mes, unidades)

    try:
        comparativas = met.comparar_periodos(reservas, desde, hasta)
        stats_full = {**stats, **comparativas}
    except Exception:
        stats_full = stats
    stats_full["moneda"] = "dólares (USD)" if vista == "USD" else "pesos argentinos (ARS)"
    if tc:
        stats_full["tipo_cambio"] = tc

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
    # ### CAMBIO AQUÍ ### solo en tu compu y sin modo debug (la consola de debug permite ejecutar código)
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", host="127.0.0.1", port=5000)
