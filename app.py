# app.py
import os
import re
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
                   session, flash, jsonify, abort)   # ### CAMBIO AQUÍ ### abort
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
import disposicion_pago   # ### CAMBIO AQUÍ ### cuánto más podrías cobrar
import estrategia   # ### CAMBIO AQUÍ ### qué hacer hoy
import feriados   # ### CAMBIO AQUÍ ###
import ical   # ### CAMBIO AQUÍ ### calendario de Airbnb
import pruebas   # ### CAMBIO AQUÍ ### pruebas y aprendizaje
import novedades   # ### CAMBIO AQUÍ ### historial, calendario y avisos de hoy/mañana
import alertas   # ### CAMBIO AQUÍ ### situaciones raras o pendientes

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
    MAX_CONTENT_LENGTH=15 * 1024 * 1024,   # ### CAMBIO AQUÍ ### archivos de hasta 15 MB
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


@app.template_filter("md")
def filtro_md(texto):
    """### CAMBIO AQUÍ ### muestra el texto de la IA con títulos, negritas, listas y TABLAS
    (antes se veían los ## y ** sueltos). Todo se escapa primero: no se puede meter código."""
    from markupsafe import Markup, escape

    def negrita(t):
        return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)

    html, en_lista, tabla = [], False, []

    def cerrar_tabla():
        if not tabla:
            return
        filas = [[negrita(str(escape(c.strip()))) for c in f.strip().strip("|").split("|")] for f, _ in tabla]
        con_cabecera = len(tabla) > 1 and tabla[0][1]
        partes = ['<div class="table-wrap"><table class="tabla tabla-ia">']
        if con_cabecera:
            partes.append("<thead><tr>" + "".join(f"<th>{c}</th>" for c in filas[0]) + "</tr></thead>")
            filas = filas[1:]
        partes.append("<tbody>" + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>" for f in filas) + "</tbody></table></div>")
        html.append("".join(partes))
        tabla.clear()

    for linea in str(texto or "").split("\n"):
        l = linea.strip()
        if re.match(r"^\|?\s*:?-{3,}", l):   # línea separadora de una tabla: marca que la fila anterior era cabecera
            if tabla:
                tabla[-1] = (tabla[-1][0], True)
            continue
        if l.startswith("|"):
            if en_lista:
                html.append("</ul>")
                en_lista = False
            tabla.append((l, False))
            continue
        cerrar_tabla()
        es_item = l.startswith(("- ", "* ", "• "))
        if en_lista and not es_item:
            html.append("</ul>")
            en_lista = False
        t = negrita(str(escape(l[2:] if es_item else l)))
        if not l:
            continue
        if l.startswith("#"):
            nivel = len(l) - len(l.lstrip("#"))
            t = str(escape(l.lstrip("#").strip()))
            t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
            html.append(f"<h3>{t}</h3>" if nivel <= 2 else f"<h4>{t}</h4>")
        elif es_item:
            if not en_lista:
                html.append("<ul>")
                en_lista = True
            html.append(f"<li>{t}</li>")
        else:
            html.append(f"<p>{t}</p>")
    cerrar_tabla()
    if en_lista:
        html.append("</ul>")
    return Markup("\n".join(html))


@app.template_filter("monto_input")
def filtro_monto_input(valor, vacio=""):
    """### CAMBIO AQUÍ ### valor para un campo de texto: 15000 → '15000', 4.85 → '4,85', None → ''."""
    from jinja2 import Undefined
    if valor is None or valor == "" or isinstance(valor, Undefined):
        return vacio
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    return str(int(v)) if v == int(v) else f"{v:.2f}".rstrip("0").replace(".", ",")


@app.template_filter("num")
def filtro_num(valor, decimales=1):
    # ### CAMBIO AQUÍ ### — números con coma decimal: 70,8 (antes 70.8)
    from jinja2 import Undefined
    if valor is None or valor == "" or isinstance(valor, Undefined):
        return "—"
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    from decimal import Decimal, ROUND_HALF_UP
    v = float(Decimal(str(v)).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP))   # 12,5 → 13
    if v == 0:
        v = 0.0   # ### CAMBIO AQUÍ ### evita "-0"
    txt = f"{v:,.{decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if decimales and txt.endswith("," + "0" * decimales):
        txt = txt[: -(decimales + 1)]
    return txt


def _costos_y_unidades(prop_id, vista="ARS", tc=None, avisar=False):
    """Costos fijos mensuales (en la moneda 'vista') y cantidad de unidades.
    ### CAMBIO AQUÍ ### las propiedades INACTIVAS no cuentan (como dice la ayuda), salvo que se elija esa misma."""
    props = (db.query("SELECT * FROM propiedades WHERE id=%s", (prop_id,)) if prop_id
             else db.query("SELECT * FROM propiedades WHERE COALESCE(estado,'activa') <> 'inactiva'"))
    faltan = []
    costos = monedas.costos_mensuales(props, vista, tc, faltan)
    if faltan and avisar:
        flash(f"Los costos fijos de {', '.join(faltan)} están en otra moneda y no se descontaron: "
              f"cargá el tipo de cambio (arriba a la derecha).", "warn")
    return costos, max(len(props), 1)


def _rango_fechas(desde_txt, hasta_txt, desde_def, hasta_def):
    """### CAMBIO AQUÍ ### fechas del filtro validadas: vacías o mal escritas → las de siempre;
    invertidas → se dan vuelta. Antes una fecha rara daba error 500."""
    d1 = met.fecha_valida(desde_txt) or desde_def
    d2 = met.fecha_valida(hasta_txt) or hasta_def
    if (desde_txt and not met.fecha_valida(desde_txt)) or (hasta_txt and not met.fecha_valida(hasta_txt)):
        flash("Una de las fechas no era válida: se usó la fecha por defecto.", "warn")
    if d1 > d2:
        d1, d2 = d2, d1
        flash("La fecha 'desde' era posterior a 'hasta': se dieron vuelta.", "warn")
    return d1.isoformat(), d2.isoformat()


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


@app.context_processor
def inyectar_hoy():
    """### CAMBIO AQUÍ ### número de llegadas + salidas de hoy, para el menú (Calendario)."""
    if not session.get("logged_in"):
        return {}
    return {"movimientos_hoy": novedades.cantidad_hoy()}


@app.template_filter("hace")
def filtro_hace(cuando):
    """### CAMBIO AQUÍ ### 'hace 5 minutos', 'hace 2 horas', 'hace 3 días'."""
    from datetime import timezone as _tz
    if not cuando or not hasattr(cuando, "tzinfo"):
        return ""
    ahora = datetime.now(_tz.utc) if cuando.tzinfo else datetime.now()
    seg = max(0, int((ahora - cuando).total_seconds()))
    if seg < 60:
        return "recién"
    if seg < 3600:
        n = seg // 60
        return f"hace {n} minuto{'s' if n > 1 else ''}"
    if seg < 86400:
        n = seg // 3600
        return f"hace {n} hora{'s' if n > 1 else ''}"
    n = seg // 86400
    return f"hace {n} día{'s' if n > 1 else ''}"


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
    return _volver_referrer()   # ### CAMBIO AQUÍ ### solo a páginas de este sitio


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
    return _volver_referrer()   # ### CAMBIO AQUÍ ### solo a páginas de este sitio


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


def destino_interno(url):
    """### CAMBIO AQUÍ ### SEGURIDAD: True solo para direcciones de este mismo sitio ("/hoy?x=1").
    Antes "/\\otro-sitio.com" pasaba el control y el navegador lo trataba como otro sitio (redirección abierta)."""
    from urllib.parse import urlsplit
    if not url or not url.startswith("/") or url[1:2] in ("/", "\\"):
        return False
    if any(ord(c) < 32 or c == "\\" for c in url):
        return False
    u = urlsplit(url)
    return not u.scheme and not u.netloc


def _volver_referrer(defecto="dashboard"):
    """### CAMBIO AQUÍ ### vuelve a la página anterior solo si era de este sitio."""
    from urllib.parse import urlsplit
    ref = request.referrer or ""
    u = urlsplit(ref)
    if u.netloc and u.netloc == request.host:
        destino = u.path + ("?" + u.query if u.query else "")
        if destino_interno(destino):
            return redirect(destino)
    return redirect(url_for(defecto))


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
    # ### CAMBIO AQUÍ ### las páginas con datos del negocio no se guardan en cachés intermedias ni en el navegador
    if session.get("logged_in") and resp.mimetype in ("text/html", "application/json"):
        resp.headers["Cache-Control"] = "no-store"
        resp.headers.add("Vary", "Cookie")
    return resp


# ### CAMBIO AQUÍ ### — páginas de error en castellano, con botón para volver (antes: texto en inglés, sin menú)
@app.errorhandler(404)
def error_404(e):
    return render_template("error.html", titulo="No encontramos esa página",
                           texto="El link puede estar mal escrito o lo que buscabas ya no existe."), 404


@app.errorhandler(413)
def error_413(e):
    flash("El archivo es demasiado grande (máximo 15 MB). ¿Seguro es el CSV de Airbnb?", "error")
    return redirect(url_for("importar"))


@app.errorhandler(500)
def error_500(e):
    return render_template("error.html", titulo="Algo salió mal",
                           texto="Hubo un error inesperado. Probá de nuevo en un minuto. "
                                 "Si se repite, avisale a Pedro qué estabas haciendo."), 500


# ── Inicializar DB al arrancar ───────────────────────────────────────────────
with app.app_context():
    db.init_db()


# ── Decorador de login ───────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            # ### CAMBIO AQUÍ ### después de ingresar vuelve a la página donde estaba
            if request.method == "GET":
                session["volver_a"] = request.full_path
            flash("Ingresá con tu usuario y contraseña para continuar.", "warn")
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
            volver = session.get("volver_a") or ""
            session.clear()
            session["logged_in"] = True
            session.permanent = True   # vence a las 12 horas
            # solo rutas internas (nunca otro sitio)
            if destino_interno(volver) and not volver.startswith("/login"):   # ### CAMBIO AQUÍ ###
                return redirect(volver)
            return redirect(url_for("hoy"))   # ### CAMBIO AQUÍ ### al entrar, primero "Qué hacer hoy"
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

    hoy = date.today()
    desde, hasta = _rango_fechas(request.args.get("desde"), request.args.get("hasta"),
                                 date(hoy.year, hoy.month, 1), hoy)
    prop_id = request.args.get("propiedad_id", None, type=int)

    # ### CAMBIO AQUÍ ### — los montos se pasan a la moneda elegida (ARS o USD)
    vista, tc = moneda_vista(), monedas.tc_valor()
    reservas = db.query("SELECT * FROM reservas")
    reservas_filtradas = met.filtrar_reservas(reservas, desde, hasta, prop_id)
    reservas_filtradas, sin_tc = monedas.convertir_reservas(reservas_filtradas, vista, tc)
    if sin_tc:
        flash(f"{sin_tc} reservas están en otra moneda: cuentan en noches y ocupación, pero sus montos no se "
              f"sumaron. Cargá el tipo de cambio (arriba a la derecha).", "warn")

    costos_mes, unidades = _costos_y_unidades(prop_id, vista, tc, avisar=False)   # ### CAMBIO AQUÍ ### ya lo dice la alerta "Falta el tipo de cambio"
    stats = met.calcular_metricas(reservas_filtradas, desde, hasta, costos_mes, unidades)
    # ### CAMBIO AQUÍ ### el gráfico por mes muestra al menos los últimos 12 meses
    g1, g2 = met.ventana_grafico(desde, hasta)
    todas_conv, _ = monedas.convertir_reservas(met.filtrar_reservas(reservas, g1, g2, prop_id), vista, tc)
    por_mes = met.metricas_por_mes(todas_conv, prop_id, g1, g2)

    informes = db.query("SELECT id, titulo, creado_en FROM informes ORDER BY creado_en DESC LIMIT 5")

    # ### CAMBIO AQUÍ ### — próximas reservas, reseñas pendientes y ocupación de los últimos 7 días
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

    al_vis, al_ocu = _alertas_seguras(prop_id)   # ### CAMBIO AQUÍ ### las ocultadas van aparte
    return render_template("dashboard.html",
        propiedades=propiedades, stats=stats, por_mes=por_mes,   # ### CAMBIO AQUÍ ### se escapa con |tojson
        alerta_comp=competencia_auto.alerta_sin_datos(),   # ### CAMBIO AQUÍ ### aviso si la competencia no se actualiza
        archivo_pendiente=archivo_anual.anio_pendiente(),   # ### CAMBIO AQUÍ ### aviso del archivo anual
        desde=desde, hasta=hasta, prop_id=prop_id, informes=informes,
        proximas=proximas, resenas_pend=resenas_pend, ocup_7=ocup_7, hay_reservas=bool(reservas),
        avisos=novedades.avisos(prop_id),   # ### CAMBIO AQUÍ ### hoy / mañana / novedades
        alertas=al_vis, alertas_ocultas=al_ocu)


def _alertas_seguras(prop_id):
    """### CAMBIO AQUÍ ### si una revisión falla, el Dashboard igual se muestra. Devuelve (visibles, ocultas)."""
    try:
        return alertas.separar(alertas.revisar(prop_id))
    except Exception as e:
        print(f"[alertas] {e}")
        return [], []


def _volver_al_dashboard():
    destino = request.form.get("volver") or ""
    return redirect(destino if destino_interno(destino) else url_for("dashboard"))   # ### CAMBIO AQUÍ ###


# ════════════════════════════════════════════════════════════════════════════
# ### CAMBIO AQUÍ ### QUÉ HACER HOY y ESTRATEGIA
# ════════════════════════════════════════════════════════════════════════════
TIPOS_PRUEBA = {k: v[0] for k, v in pruebas.TIPOS.items()}   # ### CAMBIO AQUÍ ### tipos nuevos (pruebas.py)
app.jinja_env.globals["TIPOS_PRUEBA"] = TIPOS_PRUEBA
app.jinja_env.globals["UNIDAD_PRUEBA"] = {k: v[1] for k, v in pruebas.TIPOS.items()}


def _volver(defecto):
    destino = request.form.get("volver") or ""
    return redirect(destino if destino_interno(destino) else defecto)   # ### CAMBIO AQUÍ ###


def _leer_calendario(p):
    try:
        ical.actualizar(p)
    except Exception as e:
        print(f"[ical] {p.get('id')}: {e}")


def _refrescar_calendarios(props, espera=6.0):
    """Lee los calendarios de Airbnb que tengan más de una hora (en paralelo, sin trabar la página)."""
    import threading
    hilos = [threading.Thread(target=_leer_calendario, args=(p,), daemon=True)
             for p in props if (p.get("ical_url") or "").strip()]
    limite = time.monotonic() + espera
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(max(0.0, limite - time.monotonic()))


def _analisis_estrategia(props, hoy):
    reservas = db.query("SELECT * FROM reservas")
    tc = monedas.tc_valor()
    try:
        lista_esp, origen_fer = feriados.proximos(hoy, estrategia.DIAS_ADELANTE)
    except Exception as e:
        print(f"[feriados] {e}")
        lista_esp, origen_fer = [], "sin datos"
    try:
        evaluadas = pruebas.evaluar_todas(hoy, tc)   # ### CAMBIO AQUÍ ### una sola vez para todas las propiedades
    except Exception as e:
        print(f"[pruebas] {e}")
        evaluadas = []
    out = []
    for p in props:
        try:
            out.append(estrategia.analizar(p, reservas, hoy, tc, lista_esp, evaluadas))
        except Exception as e:
            print(f"[estrategia] {p.get('id')}: {e}")
    return out, lista_esp, origen_fer


@app.route("/hoy")
@login_required
def hoy():
    dia = date.today()
    props = db.query("SELECT * FROM propiedades WHERE COALESCE(estado,'activa') = 'activa' ORDER BY nombre")
    _refrescar_calendarios(props)
    props = db.query("SELECT * FROM propiedades WHERE COALESCE(estado,'activa') = 'activa' ORDER BY nombre")
    analisis, lista_esp, origen_fer = _analisis_estrategia(props, dia)
    bloques, claves = [], ["eventos"]
    for a in analisis:
        pid = a["prop"]["id"]
        try:
            acc = estrategia.acciones(a)
        except Exception as e:
            print(f"[estrategia] acciones {pid}: {e}")
            acc = []
        try:
            sit = estrategia.situacion(a)   # ### CAMBIO AQUÍ ### techo, descuentos y disponibilidad
        except Exception as e:
            print(f"[estrategia] situación {pid}: {e}")
            sit = None
        cal_cuando, cal_error = ical.ultimo(pid) if (a["prop"].get("ical_url") or "").strip() else (None, "")
        bloques.append({"prop": a["prop"], "a": a, "sit": sit, "acciones": acc, "cal_cuando": cal_cuando, "cal_error": cal_error,
                        "por": {c: [x for x in acc if x["cuando"] == c] for c in ("hoy", "semana", "mes")}})
        claves += [x["clave"] for x in acc] + [f"{pid}:{k}" for k in ("techo", "descuentos", "disponibilidad",
                                                                       "recambio", "estadia", "precios")]
    f_imp = db.query_one("SELECT valor FROM config WHERE clave='ultima_importacion_reservas'")
    # ### CAMBIO AQUÍ ### plata en juego: suma del impacto de las tareas de hoy, en la moneda elegida arriba
    vista, tc = moneda_vista(), monedas.tc_valor()
    en_juego, sin_tc = 0, {}
    for b in bloques:
        for x in b["acciones"]:
            if x.get("impacto") and x["cuando"] == "hoy":
                v = monedas.convertir(x["impacto"]["monto"], x["impacto"]["mon"], vista, tc)
                if v is None:
                    sin_tc[x["impacto"]["mon"]] = sin_tc.get(x["impacto"]["mon"], 0) + x["impacto"]["monto"]
                else:
                    en_juego += v
    juego_txt = " + ".join([monedas.formatear(en_juego, vista)] * bool(en_juego)
                           + [monedas.formatear(v, m) for m, v in sin_tc.items()])
    return render_template("hoy.html", bloques=bloques, dia=dia, coment=estrategia.comentarios(claves),
                           ultima_reservas=(f_imp or {}).get("valor"), hay_props=bool(props), esp=lista_esp,
                           origen_fer=origen_fer, total=sum(len(b["acciones"]) for b in bloques), juego_txt=juego_txt)


@app.route("/estrategia")
@login_required
def estrategia_pagina():
    """### CAMBIO AQUÍ ### la página Estrategia se unificó con "Qué hacer hoy": los links viejos siguen andando."""
    pid = request.args.get("propiedad_id", type=int)
    viejo = request.args.get("resaltar") or ""
    if viejo == "pruebas":
        return redirect(url_for("pruebas_pagina"))
    if pid and viejo in ("precios", "estadia", "descuentos", "recambio"):
        return redirect(url_for("hoy", resaltar=f"{viejo}-{pid}"))
    return redirect(url_for("hoy", resaltar=f"prop-{pid}") if pid else url_for("hoy"))


@app.route("/acciones/estado", methods=["POST"])
@login_required
def accion_estado():
    clave = (request.form.get("clave") or "").strip()[:200]
    estado = request.form.get("estado")
    if clave and estado in ("hecho", "descartado"):
        db.execute("""INSERT INTO acciones_estado (clave, estado, fecha) VALUES (%s, %s, %s)
                      ON CONFLICT (clave) DO UPDATE SET estado = EXCLUDED.estado, fecha = EXCLUDED.fecha""",
                   (clave, estado, date.today().isoformat()))
        msg = "Marcado como hecho." if estado == "hecho" else "Sugerencia descartada."
        # ### CAMBIO AQUÍ ### lo hecho se anota solo como prueba (para ver si funcionó y aprender)
        if estado == "hecho" and request.form.get("p_tipo"):
            try:
                ok, m = _guardar_prueba(request.form.get("p_pid", type=int), request.form.get("p_tipo"), date.today(),
                                        request.form.get("p_valor", type=float), met.fecha_valida(request.form.get("p_desde")),
                                        met.fecha_valida(request.form.get("p_hasta")), "", "hecho", clave,
                                        request.form.get("p_sugerido", type=float))
                if ok:
                    msg += " Quedó anotado en Pruebas."
            except Exception as e:
                print(f"[pruebas] desde hecho: {e}")
        flash(msg, "success")
    return _volver(url_for("hoy"))


@app.route("/comentarios", methods=["POST"])
@login_required
def comentar():
    clave = (request.form.get("clave") or "").strip()[:200]
    texto = (request.form.get("texto") or "").strip()[:1000]
    if clave and texto:
        db.execute("INSERT INTO comentarios (clave, texto) VALUES (%s, %s)", (clave, texto))
        flash("Comentario guardado. El Asistente IA lo va a tener en cuenta.", "success")
    elif clave:
        flash("Escribí algo en el comentario.", "warn")
    return _volver(url_for("hoy"))


@app.route("/comentarios/<int:cid>/eliminar", methods=["POST"])
@login_required
def comentario_eliminar(cid):
    db.execute("DELETE FROM comentarios WHERE id=%s", (cid,))
    return _volver(url_for("hoy"))


# ### CAMBIO AQUÍ ### PRUEBAS: sección propia (anotar, ver si funcionó y lo que aprendió el sistema)
@app.route("/pruebas")
@login_required
def pruebas_pagina():
    tc = monedas.tc_valor()
    props = db.query("SELECT * FROM propiedades ORDER BY (COALESCE(estado,'activa') = 'inactiva'), nombre")
    evaluadas = pruebas.evaluar_todas(date.today(), tc)
    aprendido = []
    for p in props:
        a = pruebas.aprendizaje(p["id"], evaluadas)
        lec = pruebas.lecciones(p["id"], evaluadas)
        if a or lec:
            aprendido.append({"prop": p, "a": a, "lecciones": lec})
    return render_template("pruebas.html", propiedades=props, evaluadas=evaluadas, aprendido=aprendido,
                           esperando=[x for x in evaluadas if x["color"] == "⚪"],
                           resultados=[x for x in evaluadas if x["color"] != "⚪"],
                           hoy_iso=date.today().isoformat(), pid_sel=request.args.get("propiedad_id", type=int))


def _guardar_prueba(pid, tipo, fecha, valor, desde, hasta, nota="", origen="manual", clave=None, sugerido=None):
    """Valida y guarda una prueba. Devuelve (ok, mensaje)."""
    prop = db.query_one("SELECT * FROM propiedades WHERE id=%s", (pid,)) if pid else None
    if not prop:
        return False, "Elegí la propiedad."
    if tipo not in pruebas.TIPOS:
        return False, "Elegí qué cambiaste."
    if not fecha or fecha > date.today():
        return False, "La fecha del cambio no puede ser futura."
    unidad = pruebas.TIPOS[tipo][1]
    if unidad == "$" and not (valor and valor > 0):
        return False, "Poné el precio por noche que pusiste en Airbnb."
    if unidad == "%" and valor is not None and not (0 <= valor <= 90):
        return False, "El porcentaje tiene que estar entre 0 y 90."
    if unidad == "noches" and not (valor and 1 <= valor <= 365 and valor == int(valor)):
        return False, "La estadía mínima tiene que ser un número de noches entre 1 y 365."
    if tipo == "precio" and not desde:
        return False, "Para un precio, poné para qué fechas (desde y hasta)."
    if desde and hasta and hasta < desde:
        return False, "La fecha 'hasta' no puede ser anterior a 'desde'."
    if desde and (hasta or desde) - desde > timedelta(days=120):
        return False, "Una prueba puede abarcar como mucho 120 noches."
    if clave and db.query_one("SELECT id FROM pruebas_descuento WHERE clave=%s", (clave,)):
        return True, "ya estaba anotada"
    if tipo == "precio" and sugerido is None:
        try:   # cuánto sugería el sistema ese día para esa fecha (sin el ajuste aprendido)
            a = estrategia.analizar(prop, db.query("SELECT * FROM reservas WHERE propiedad_id=%s", (pid,)), date.today(),
                                    monedas.tc_valor(), None, [])
            sugerido, _ = estrategia.precio_noche(desde, a["cx"], aprender=False)
        except Exception as e:
            print(f"[pruebas] sugerido: {e}")
            sugerido = None
    otra = pruebas.superpuesta(pid, tipo, fecha, desde, hasta or desde)
    db.execute("""INSERT INTO pruebas_descuento (propiedad_id, fecha, tipo, porcentaje, nota, desde, hasta, valor, sugerido, origen, clave)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
               (pid, fecha.isoformat(), tipo, valor if unidad == "%" else 0, (nota or "")[:300],
                desde.isoformat() if desde else None, (hasta or desde).isoformat() if desde else None,
                valor, sugerido, origen, clave))
    if otra:
        return True, (f"Anotada. Ojo: ya hay otra prueba en {prop['nombre']} cerca de esas fechas "
                      f"({pruebas.nombre_tipo(otra['tipo'])}); los resultados se pueden mezclar.")
    return True, "Prueba anotada. Cuando pasen las fechas (o se reserven) vas a ver si funcionó."


@app.route("/pruebas/nueva", methods=["POST"])
@login_required
def prueba_nueva():
    txt = (request.form.get("valor") or "").strip()
    valor = importador.parsear_monto(txt) if txt else None
    ok, msg = _guardar_prueba(request.form.get("propiedad_id", type=int), request.form.get("tipo"),
                              met.fecha_valida(request.form.get("fecha")), valor,
                              met.fecha_valida(request.form.get("desde")), met.fecha_valida(request.form.get("hasta")),
                              (request.form.get("nota") or "").strip())
    flash(msg, ("warn" if "Ojo" in msg else "success") if ok else "error")
    return redirect(url_for("pruebas_pagina"))


@app.route("/pruebas/<int:prid>/eliminar", methods=["POST"])
@login_required
def prueba_eliminar(prid):
    db.execute("DELETE FROM pruebas_descuento WHERE id=%s", (prid,))
    flash("Prueba borrada.", "success")
    return redirect(url_for("pruebas_pagina"))


@app.route("/pruebas/aprendizaje/<int:pid>", methods=["POST"])
@login_required
def prueba_aprendizaje(pid):
    """Prender o apagar el ajuste aprendido de una propiedad."""
    if request.form.get("activar") == "1":
        db.execute("DELETE FROM config WHERE clave=%s", (f"aprendizaje_off_{pid}",))
        flash("Listo: el ajuste aprendido vuelve a usarse en los precios sugeridos.", "success")
    else:
        db.execute("""INSERT INTO config (clave, valor) VALUES (%s, '1')
                      ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor""", (f"aprendizaje_off_{pid}",))
        flash("Listo: los precios sugeridos ya no usan el ajuste aprendido.", "success")
    return redirect(url_for("pruebas_pagina"))


@app.route("/eventos", methods=["POST"])
@login_required
def evento_nuevo():
    d1 = met.fecha_valida(request.form.get("desde"))
    d2 = met.fecha_valida(request.form.get("hasta")) or d1
    nombre = (request.form.get("nombre") or "").strip()[:80]
    try:
        impacto = int(request.form.get("impacto") or 10)
    except ValueError:
        impacto = None
    if not d1 or not d2 or d2 < d1 or (d2 - d1).days > 60 or not nombre or impacto is None or not (-50 <= impacto <= 100):
        flash("No se guardó el evento: revisá las fechas (hasta 60 días), el nombre y el impacto (de -50 a 100).", "error")
    else:
        db.execute("INSERT INTO eventos (desde, hasta, nombre, impacto) VALUES (%s,%s,%s,%s)",
                   (d1.isoformat(), d2.isoformat(), nombre, impacto))
        flash("Evento guardado: ya se usa en los precios sugeridos.", "success")
    return _volver(url_for("hoy"))


@app.route("/eventos/<int:eid>/eliminar", methods=["POST"])
@login_required
def evento_eliminar(eid):
    db.execute("DELETE FROM eventos WHERE id=%s", (eid,))
    return _volver(url_for("hoy"))


@app.route("/calendario-airbnb/<int:pid>/link", methods=["POST"])
@login_required
def ical_link(pid):
    """### CAMBIO AQUÍ ### pegar el link del calendario desde Importar (y leerlo en el momento)."""
    prop = db.query_one("SELECT * FROM propiedades WHERE id=%s", (pid,))
    url = (request.form.get("ical_url") or "").strip()[:500]
    if not prop:
        return redirect(url_for("importar"))
    ok, msg = ical.url_valida(url)
    if not ok:
        flash(msg, "error")
        return redirect(url_for("importar", resaltar=f"ical-{pid}"))
    db.execute("UPDATE propiedades SET ical_url=%s WHERE id=%s", (url, pid))
    if not url:
        db.execute("DELETE FROM ical_bloqueos WHERE propiedad_id=%s", (pid,))
        db.execute("DELETE FROM config WHERE clave=%s", (f"ical_leido_{pid}",))
        flash(f"Se desconectó el calendario de {prop['nombre']}.", "success")
        return redirect(url_for("importar", resaltar="subir-calendario"))
    try:
        leido, info_ = ical.actualizar({**prop, "ical_url": url}, forzar=True)
    except Exception as e:
        leido, info_ = False, str(e)[:150]
    if leido:
        flash(f"Calendario de {prop['nombre']} conectado y leído ({info_}).", "success")
    else:
        flash(f"Se guardó el link de {prop['nombre']}, pero no se pudo leer: {info_}. Revisá que sea el de 'Exportar calendario'.", "error")
    return redirect(url_for("importar", resaltar=f"ical-{pid}"))


@app.route("/calendario-airbnb/<int:pid>/leer", methods=["POST"])
@login_required
def ical_leer(pid):
    prop = db.query_one("SELECT * FROM propiedades WHERE id=%s", (pid,))
    if prop:
        try:
            ok, msg = ical.actualizar(prop, forzar=True)
        except Exception as e:
            ok, msg = False, str(e)[:150]
        flash("Calendario de Airbnb leído." if ok else f"No se pudo leer el calendario: {msg}", "success" if ok else "error")
    return _volver(url_for("hoy"))


# ### CAMBIO AQUÍ ### BORRAR TODOS LOS DATOS (solo para servicios de prueba)
# Apagado por defecto: solo existe si en Render se agrega la variable PERMITIR_BORRAR_TODO=si.
# En el servicio de Adriano NO se pone esa variable, así nunca puede borrar todo por error.
TABLAS_DATOS = ["reservas_historial", "movimientos_airbnb", "reservas", "competencia_historial", "competencia",
                "consultas_huespedes", "resenas", "informes", "temporadas", "propiedades", "config", "login_intentos",
                "ical_bloqueos", "comentarios", "acciones_estado", "pruebas_descuento", "eventos"]   # ### CAMBIO AQUÍ ###
FRASE_BORRAR = "BORRAR TODO"


def _borrar_permitido():
    return os.environ.get("PERMITIR_BORRAR_TODO", "").strip().lower() in ("si", "sí", "1", "true")


@app.route("/borrar-todo", methods=["GET", "POST"])
@login_required
def borrar_todo():
    if not _borrar_permitido():
        abort(404)
    if request.method == "POST":
        frase_ok = (request.form.get("frase") or "").strip().upper() == FRASE_BORRAR
        clave_ok = hmac.compare_digest((request.form.get("password") or "").encode(), ADMIN_PASS.encode())
        if not (frase_ok and clave_ok):
            flash(f"No se borró nada: escribí exactamente {FRASE_BORRAR} y tu contraseña.", "error")
            return redirect(url_for("borrar_todo"))
        db.execute("SET lock_timeout = '10s'; TRUNCATE " + ", ".join(TABLAS_DATOS) + " RESTART IDENTITY CASCADE")
        db.init_db()   # vuelve a poner la configuración inicial
        flash("Listo: se borraron todos los datos. El sistema quedó vacío, como recién instalado.", "success")
        return redirect(url_for("dashboard"))
    return render_template("borrar_todo.html", frase=FRASE_BORRAR,
        cuenta={t: db.query_one(f"SELECT COUNT(*) AS n FROM {t}")["n"]
                for t in ("propiedades", "reservas", "movimientos_airbnb", "competencia", "resenas", "consultas_huespedes", "informes")})


# ### CAMBIO AQUÍ ### ocultar una alerta por unos días / volver a mostrarlas
@app.route("/alertas/ocultar", methods=["POST"])
@login_required
def alerta_ocultar():
    alertas.ocultar(request.form.get("clave", "").strip())
    flash(f"Alerta ocultada por {alertas.DIAS_OCULTA} días. Si el problema sigue, vuelve a aparecer.", "success")
    return _volver_al_dashboard()


@app.route("/alertas/mostrar", methods=["POST"])
@login_required
def alerta_mostrar():
    alertas.mostrar_todas()
    return _volver_al_dashboard()


# ════════════════════════════════════════════════════════════════════════════
# ### CAMBIO AQUÍ ### CALENDARIO
# ════════════════════════════════════════════════════════════════════════════
MESES_LARGOS = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
                "Septiembre", "Octubre", "Noviembre", "Diciembre"]


@app.route("/calendario")
@login_required
def calendario():
    import calendar as cal
    hoy = date.today()
    # ### CAMBIO AQUÍ ### dos vistas: "mes" (almanaque) y "linea" (línea de tiempo por propiedad). Se recuerda la última.
    vista = request.args.get("vista")
    if vista in ("mes", "linea"):
        session["cal_vista"] = vista
    vista = session.get("cal_vista", "mes")
    if vista == "linea":
        return _calendario_linea(hoy)
    txt = request.args.get("mes") or ""
    try:
        anio, mes_n = int(txt[:4]), int(txt[5:7])
        if not (2000 <= anio <= 2100 and 1 <= mes_n <= 12):
            raise ValueError
    except ValueError:
        anio, mes_n = hoy.year, hoy.month
    prop_id = request.args.get("propiedad_id", type=int)
    dias, unidades = novedades.mes(anio, mes_n, prop_id)
    semanas = cal.Calendar(firstweekday=0).monthdatescalendar(anio, mes_n)   # semanas de lunes a domingo
    ant = date(anio, mes_n, 1) - timedelta(days=1)
    sig = date(anio, mes_n, cal.monthrange(anio, mes_n)[1]) + timedelta(days=1)
    return render_template("calendario.html", vista="mes", dias=dias, semanas=semanas, anio=anio, mes_n=mes_n,
                           titulo=f"{MESES_LARGOS[mes_n - 1]} {anio}", hoy=hoy.isoformat(), unidades=unidades,
                           ant=f"{ant.year}-{ant.month:02d}", sig=f"{sig.year}-{sig.month:02d}",
                           propiedades=db.query("SELECT id, nombre FROM propiedades ORDER BY nombre"), prop_id=prop_id,
                           seleccionado=request.args.get("dia") or (hoy.isoformat() if (hoy.year, hoy.month) == (anio, mes_n) else ""))


@app.route("/ajustes")
@login_required
def ajustes():
    """### CAMBIO AQUÍ ### modo oscuro, tamaño de letra, alto contraste y menos animaciones (se guardan en el dispositivo)."""
    return render_template("ajustes.html")


LINEA_DIAS = 14


def _calendario_linea(hoy):
    """### CAMBIO AQUÍ ### línea de tiempo: una fila por propiedad, 14 días. Ocupado según reservas + calendario de Airbnb
    (lo mismo que usa "Qué hacer hoy"); en lo libre, el precio sugerido y los huecos que nadie puede reservar."""
    desde = met.fecha_valida(request.args.get("desde")) or hoy
    desde = max(hoy, min(desde, hoy + timedelta(days=estrategia.DIAS_ADELANTE - LINEA_DIAS)))
    prop_id = request.args.get("propiedad_id", type=int)
    todas = db.query("SELECT * FROM propiedades WHERE COALESCE(estado,'activa') = 'activa' ORDER BY nombre")
    props = [p for p in todas if not prop_id or p["id"] == prop_id]
    _refrescar_calendarios(props)   # lee el calendario de Airbnb si hace más de una hora
    props = [p for p in db.query("SELECT * FROM propiedades WHERE COALESCE(estado,'activa') = 'activa' ORDER BY nombre")
             if not prop_id or p["id"] == prop_id]
    analisis, _, _ = _analisis_estrategia(props, hoy)
    reservas = [r for r in db.query("SELECT * FROM reservas WHERE COALESCE(estado,'') <> 'cancelada'")]
    dias = [desde + timedelta(days=k) for k in range(LINEA_DIAS)]
    filas = []
    for a in analisis:
        prop, mon = a["prop"], a["h"]["mon"]
        minima = prop.get("estadia_minima")
        propias = []
        for r in reservas:
            if r["propiedad_id"] == prop["id"]:
                fi, ff, n = met._rango(r)
                if fi and ff:
                    propias.append((fi, ff, n, r))

        def reserva_de(d):
            for fi, ff, n, r in propias:
                if fi <= d < ff:
                    return fi, ff, n, r
            return None

        def tramo_de(d):
            for t in a["libres"]:
                if t[0] <= d <= t[1]:
                    return t
            return None

        claves = []
        for d in dias:
            if d in a["ocup"]:
                rr = reserva_de(d)
                claves.append(("ocup", rr[3]["id"] if rr else None))
            else:
                claves.append(("libre", None))
        segs, k = [], 0
        while k < len(dias):
            j = k
            while j + 1 < len(dias) and claves[j + 1] == claves[k]:
                j += 1
            d1, d2, n = dias[k], dias[j], j - k + 1
            seg = {"col": k + 2, "span": n, "desde": d1, "hasta": d2}
            if claves[k][0] == "ocup":
                rr = reserva_de(d1)
                if rr:
                    nombre = (rr[3].get("huesped_nombre") or "Huésped").split(" ")[0]
                    seg.update(clase="ocupado", txt=nombre, sub=f"{rr[2]} noche{'s' if rr[2] != 1 else ''}",
                               aria=f"Reservado: {nombre}, del {rr[0].strftime('%d/%m')} al {rr[1].strftime('%d/%m')}")
                else:
                    seg.update(clase="ocupado bloqueado", txt="Ocupado", sub="según Airbnb",
                               aria="Ocupado según el calendario de Airbnb")
            else:
                precios = [estrategia.precio_noche(d, a["cx"])[0] for d in dias[k:j + 1]]
                precios = [p for p in precios if p]
                t = tramo_de(d1)
                largo = (t[1] - t[0]).days + 1 if t else n
                corto = bool(t and t[2] and minima and largo < minima)
                if precios:
                    lo, hi = min(precios), max(precios)
                    ptxt = monedas.formatear(lo, mon) + ("" if lo == hi else " a " + monedas.formatear(hi, mon))
                else:
                    ptxt = "sin precio base"
                seg.update(clase="libre corto" if corto else "libre",
                           txt=(f"{largo} noche{'s' if largo != 1 else ''}: nadie puede reservar" if corto else "Libre"),
                           sub=ptxt, aria=("Libre, más corto que la estadía mínima. " if corto else "Libre. ") + "Precio sugerido " + ptxt)
            segs.append(seg)
            k = j + 1
        filas.append({"prop": prop, "segs": segs, "fuente": a["fuente"]})
    ant = desde - timedelta(days=LINEA_DIAS)
    sig = desde + timedelta(days=LINEA_DIAS)
    return render_template("calendario.html", vista="linea", filas=filas, dias=dias, hoy=hoy, desde=desde,
                           ant=ant.isoformat() if ant >= hoy else (hoy.isoformat() if desde > hoy else None),
                           sig=sig.isoformat() if sig <= hoy + timedelta(days=estrategia.DIAS_ADELANTE - LINEA_DIAS) else None,
                           propiedades=todas, prop_id=prop_id, DIAS_C=["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"])


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
        ORDER BY fecha_inicio DESC LIMIT 500
    """, (ver,)) if ver else []   # ### CAMBIO AQUÍ ### se ven 12 y el resto con "Ver todas"
    hist = novedades.historial([h["codigo_confirmacion"] for h in huespedes])   # ### CAMBIO AQUÍ ###
    return render_template("propiedades.html", propiedades=props, ver=ver, huespedes=huespedes, historial=hist)


# ### CAMBIO AQUÍ ### — lectura segura del formulario de propiedad.
# Antes: "15.000" se guardaba como 15, y "2,5" o "$ 30.000" daban error 500.
COLUMNAS_PROP = ("nombre", "direccion", "barrio", "tipo", "ambientes", "capacidad", "precio_base",
                 "costo_expensas", "costo_servicios", "costo_limpieza", "costo_comision", "info_huespedes",
                 "estado", "rating", "reviews_count", "moneda", "ciudad",
                 "pais", "pais_codigo", "provincia", "piso_depto", "m2", "cochera",   # ### CAMBIO AQUÍ ###
                 "recambio_limpieza", "recambio_lavanderia", "recambio_insumos", "estadia_minima", "ical_url")   # ### CAMBIO AQUÍ ### estrategia

# ### CAMBIO AQUÍ ### tipos de alojamiento (antes solo departamento o casa)
TIPOS = {"depto": "Departamento", "monoambiente": "Monoambiente / Estudio", "loft": "Loft", "ph": "PH",
         "duplex": "Dúplex", "casa": "Casa", "cabana": "Cabaña", "quinta": "Quinta / Casa de campo",
         "habitacion": "Habitación privada", "habitacion_compartida": "Habitación compartida",
         "suite": "Suite / Hotel boutique", "otro": "Otro"}
app.jinja_env.globals["TIPOS"] = TIPOS


def _paises():
    """### CAMBIO AQUÍ ### lista de países (static/geo/paises.json), leída una sola vez."""
    if not hasattr(_paises, "lista"):
        with open(os.path.join(app.static_folder, "geo", "paises.json"), encoding="utf-8") as f:
            _paises.lista = json.load(f)
    return _paises.lista


app.jinja_env.globals["paises"] = _paises


def _leer_propiedad(f):
    """Devuelve (datos, errores) a partir del formulario."""
    errores = []

    def monto(k):
        txt = (f.get(k) or "").strip()
        if not txt:
            return 0
        v = importador.parsear_monto(txt)
        if v < 0:
            errores.append(f"El valor de '{k.replace('costo_', '').replace('_', ' ')}' no puede ser negativo.")
            return 0
        if v == 0 and re.search(r"[1-9]", txt):
            errores.append(f"No se entendió el número '{txt}'. Escribilo así: 15000 o 15.000,50")
        return v

    nombres = {"ambientes": "ambientes", "capacidad": "capacidad", "reviews_count": "cantidad de reseñas",
               "m2": "superficie (m²)", "estadia_minima": "estadía mínima (noches, de 1 a 365)"}

    def entero(k, maximo, minimo=1):
        txt = (f.get(k) or "").strip()
        if not txt:
            return None
        v = importador.parsear_monto(txt)
        if v < minimo or v > maximo or v != int(v):
            errores.append(f"'{txt}' no es un número válido para {nombres.get(k, k)} (tiene que ser un número entero).")
            return None
        return int(v)

    datos = {
        "nombre": (f.get("nombre") or "").strip()[:120],
        "direccion": (f.get("direccion") or "").strip()[:200],
        "barrio": (f.get("barrio") or "").strip()[:80],
        "tipo": f.get("tipo") if f.get("tipo") in TIPOS else "depto",
        "ambientes": entero("ambientes", 20),
        "capacidad": entero("capacidad", 50),
        "precio_base": monto("precio_base"),
        "costo_expensas": monto("costo_expensas"), "costo_servicios": monto("costo_servicios"),
        "costo_limpieza": monto("costo_limpieza"), "costo_comision": monto("costo_comision"),
        "info_huespedes": (f.get("info_huespedes") or "")[:8000],
        "estado": f.get("estado") if f.get("estado") in ("activa", "mantenimiento", "inactiva") else "activa",
        "rating": None,
        "reviews_count": entero("reviews_count", 100000, minimo=0) or 0,
        "moneda": f.get("moneda") if f.get("moneda") in monedas.MONEDAS else "ARS",
        "ciudad": (f.get("ciudad") or "").strip()[:80],
        # ### CAMBIO AQUÍ ### ubicación y características
        "pais_codigo": (f.get("pais_codigo") or "AR").strip().upper()[:2],
        "provincia": (f.get("provincia") or "").strip()[:80],
        "piso_depto": (f.get("piso_depto") or "").strip()[:40],
        "m2": entero("m2", 100000),
        "cochera": 1 if f.get("cochera") == "1" else 0,
        # ### CAMBIO AQUÍ ### costos de cada salida de huésped, estadía mínima y calendario de Airbnb
        "recambio_limpieza": monto("recambio_limpieza"), "recambio_lavanderia": monto("recambio_lavanderia"),
        "recambio_insumos": monto("recambio_insumos"),
        "estadia_minima": entero("estadia_minima", 365),
        "ical_url": (f.get("ical_url") or "").strip()[:500],
    }
    ok_ical, msg_ical = ical.url_valida(datos["ical_url"])
    if not ok_ical:
        errores.append(msg_ical)
    pais = next((p for p in _paises() if p["c"] == datos["pais_codigo"]), None)
    if not pais:
        errores.append("Elegí el país de la propiedad.")
        pais = {"c": "AR", "n": "Argentina"}
    datos["pais_codigo"], datos["pais"] = pais["c"], pais["n"]
    if not datos["ciudad"]:
        if datos["pais_codigo"] == "AR" and not datos["provincia"]:
            datos["ciudad"], datos["provincia"] = "Buenos Aires", "Ciudad Autónoma de Buenos Aires"
        else:
            errores.append("Completá la ciudad: se usa para buscar la competencia.")
    txt = (f.get("rating") or "").strip()
    if txt:
        v = importador.parsear_monto(txt)
        if 1 <= v <= 5:
            datos["rating"] = round(v, 2)
        else:
            errores.append(f"El puntaje '{txt}' tiene que estar entre 1 y 5 (ej: 4,85).")
    if not datos["nombre"]:
        errores.append("Poné un nombre a la propiedad.")
    if not datos["barrio"]:
        errores.append("Completá el barrio: sin barrio no se puede buscar la competencia.")
    return datos, errores


@app.route("/propiedades/nueva", methods=["GET","POST"])
@login_required
def nueva_propiedad():
    if request.method == "POST":
        datos, errores = _leer_propiedad(request.form)
        if errores:
            for e in errores:
                flash(e, "error")
            return render_template("propiedad_form.html", prop=None, previo=datos)
        db.execute(f"INSERT INTO propiedades ({','.join(COLUMNAS_PROP)}) VALUES ({','.join(['%s'] * len(COLUMNAS_PROP))})",
                   tuple(datos[c] for c in COLUMNAS_PROP))
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
        datos, errores = _leer_propiedad(request.form)
        if errores:
            for e in errores:
                flash(e, "error")
            return render_template("propiedad_form.html", prop={**prop, **datos})
        db.execute(f"UPDATE propiedades SET {','.join(c + '=%s' for c in COLUMNAS_PROP)} WHERE id=%s",
                   tuple(datos[c] for c in COLUMNAS_PROP) + (pid,))
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
# ### CAMBIO AQUÍ ### (revisión general) — cada archivo subido se guarda en la base con un código
# propio (antes había uno solo para todos: con dos pestañas abiertas se mezclaban los archivos).

def _pendiente_clave(token):
    return f"csv_pendiente_{token}"


def _guardar_pendiente(datos):
    import secrets
    token = secrets.token_urlsafe(9)
    datos["creado"] = datetime.now().isoformat()
    db.execute("INSERT INTO config (clave, valor) VALUES (%s, %s)", (_pendiente_clave(token), json.dumps(datos, ensure_ascii=False)))
    # limpia importaciones abandonadas (más de 1 día) y el formato viejo
    viejos = db.query("SELECT clave, valor FROM config WHERE clave LIKE 'csv_pendiente%%'")
    limite = (datetime.now() - timedelta(days=1)).isoformat()
    for v in viejos:
        try:
            creado = json.loads(v["valor"] or "{}").get("creado", "")
        except Exception:
            creado = ""
        if v["clave"] == "csv_pendiente" or creado < limite:
            db.execute("DELETE FROM config WHERE clave=%s", (v["clave"],))
    session["csv_token"] = token
    return token


def _leer_pendiente():
    # el código viaja en el formulario (?t=): así dos pestañas con archivos distintos no se mezclan
    token = request.values.get("t") or session.get("csv_token")
    if not token:
        return None, None
    row = db.query_one("SELECT valor FROM config WHERE clave=%s", (_pendiente_clave(token),))
    try:
        return token, (json.loads(row["valor"]) if row and row["valor"] else None)
    except Exception:
        return token, None


def _actualizar_pendiente(token, datos):
    db.execute("UPDATE config SET valor=%s WHERE clave=%s", (json.dumps(datos, ensure_ascii=False), _pendiente_clave(token)))


def _borrar_pendiente(token):
    db.execute("DELETE FROM config WHERE clave=%s", (_pendiente_clave(token),))
    session.pop("csv_token", None)


def _sugerir_propiedad(anuncio, propiedades, recordados):
    """Propiedad que se usó la vez pasada para ese anuncio, o la que tiene el mismo nombre."""
    if anuncio in recordados and any(p["id"] == recordados[anuncio] for p in propiedades):
        return recordados[anuncio]
    a = importador._norm(anuncio)
    for p in propiedades:
        n = importador._norm(p["nombre"])
        if n and (n == a or n in a or a in n):
            return p["id"]
    return None


def _anuncios_recordados():
    row = db.query_one("SELECT valor FROM config WHERE clave='anuncio_map'")
    try:
        return {k: int(v) for k, v in json.loads(row["valor"]).items()} if row else {}
    except Exception:
        return {}


@app.route("/importar", methods=["GET","POST"])
@login_required
def importar():
    propiedades = db.query("SELECT id, nombre FROM propiedades ORDER BY nombre")

    # resultado de la última importación (se muestra una sola vez; "actualizar" no repite nada)
    if request.method == "GET" and request.args.get("resultado"):
        res = session.pop("import_resultado", None)
        if res:
            return render_template("importar.html", propiedades=propiedades, paso=4,
                                   sin_costos=_propiedades_sin_costos(), **res)   # ### CAMBIO AQUÍ ###
        return redirect(url_for("importar"))

    if request.method == "POST":
        archivo = request.files.get("csv_file")
        if not archivo or archivo.filename == "":
            flash("Seleccioná un archivo CSV.", "error")
            return redirect(url_for("importar"))
        try:
            texto = importador.decodificar(archivo.read())
            filas = importador.leer_filas(texto)
        except importador.ArchivoInvalido as e:
            flash(str(e), "error")
            return redirect(url_for("importar"))

        encabezados = [h.strip() for h in filas[0]]
        # ### CAMBIO AQUÍ ### cada archivo se sube en su renglón: si no coincide, se avisa dónde va
        esperado = request.form.get("tipo")
        real = importador.tipo_de_archivo(encabezados)
        if esperado in ("reservas", "ganancias") and esperado != real:
            nombres = {"reservas": "Reservas", "ganancias": "Ganancias"}
            flash(f"Ese archivo es de {nombres[real]}, no de {nombres[esperado]}. "
                  f"Subilo en el renglón \"{nombres[real]}\" (está marcado abajo).", "error")
            return redirect(url_for("importar", resaltar=f"subir-{real}"))
        mapa, no_detectadas = importador.detectar_columnas(encabezados)
        token = _guardar_pendiente({"texto": texto, "encabezados": encabezados, "mapa": mapa})

        if no_detectadas:
            return render_template("importar.html", propiedades=propiedades, paso=2, token=token,
                                   encabezados=encabezados, mapa=mapa, no_detectadas=no_detectadas,
                                   etiquetas=importador.ETIQUETAS, campos=list(importador.ETIQUETAS))
        return redirect(url_for("importar_asignar", t=token))

    return render_template("importar.html", propiedades=propiedades, paso=1, frecuencia=_frecuencia_importacion(),
                           sin_costos=_propiedades_sin_costos(), calendarios=_estado_calendarios())


def _propiedades_sin_costos():
    """### CAMBIO AQUÍ ### propiedades activas sin costos cargados (Airbnb nunca los manda en los archivos)."""
    out = []
    for p in db.query("SELECT * FROM propiedades WHERE COALESCE(estado,'activa') <> 'inactiva' ORDER BY nombre"):
        falta = []
        if not any(p.get(k) for k in ("costo_expensas", "costo_servicios", "costo_limpieza", "costo_comision")):
            falta.append("costos mensuales")
        if not any(p.get(k) for k in ("recambio_limpieza", "recambio_lavanderia", "recambio_insumos")):
            falta.append("costos de recambio")
        if not p.get("barrio"):
            falta.append("barrio")
        if not p.get("precio_base"):
            falta.append("precio base")
        if falta:
            out.append({"id": p["id"], "nombre": p["nombre"], "falta": falta,
                        "campo": "costo_expensas" if "costos mensuales" in falta else
                                 ("recambio_limpieza" if "costos de recambio" in falta else
                                  ("barrio" if "barrio" in falta else "precio_base"))})
    return out


def _estado_calendarios():
    """### CAMBIO AQUÍ ### calendario de Airbnb de cada propiedad activa: link, última lectura y error."""
    props = db.query("SELECT id, nombre, ical_url FROM propiedades WHERE COALESCE(estado,'activa') = 'activa' ORDER BY nombre")
    for p in props:
        p["cuando"], p["error"] = ical.ultimo(p["id"]) if (p.get("ical_url") or "").strip() else (None, "")
    con = [p for p in props if (p.get("ical_url") or "").strip()]
    return {"total": len(props), "con": len(con), "props": props, "sin": [p for p in props if p not in con]}


# ### CAMBIO AQUÍ ### cada cuánto conviene subir cada archivo y cuándo fue la última vez
FRECUENCIA_DIAS = {"reservas": 7, "ganancias": 31}


def _frecuencia_importacion():
    out = {}
    for tipo, dias in FRECUENCIA_DIAS.items():
        row = db.query_one("SELECT valor FROM config WHERE clave=%s", (f"ultima_importacion_{tipo}",))
        ultima = met.fecha_valida(row["valor"]) if row and row["valor"] else None
        hace = (date.today() - ultima).days if ultima else None
        out[tipo] = {"ultima": ultima, "hace": hace, "vencida": hace is None or hace > dias}
    return out


@app.route("/importar/asignar", methods=["GET","POST"])
@login_required
def importar_asignar():
    propiedades = db.query("SELECT id, nombre, moneda FROM propiedades ORDER BY nombre")
    token, pend = _leer_pendiente()
    if not pend:
        # se abrió directo, se tocó dos veces o venció: no hay nada para importar
        flash("No hay ninguna importación en curso. Subí el archivo de nuevo.", "warn")
        return redirect(url_for("importar"))
    encabezados, mapa = pend["encabezados"], {k: int(v) for k, v in pend["mapa"].items()}

    # paso 2: columnas elegidas a mano
    if request.method == "POST" and "columnas" in request.form:
        for clave in importador.ETIQUETAS:
            idx = request.form.get(f"col_{clave}", type=int)
            if idx is not None and 0 <= idx < len(encabezados):
                mapa[clave] = idx
            elif f"col_{clave}" in request.form:
                mapa.pop(clave, None)
        faltan = [importador.ETIQUETAS[c] for c in importador.REQUERIDAS if c not in mapa]
        if faltan:
            flash("Falta elegir: " + ", ".join(faltan) + ". Sin esas columnas no se puede importar.", "error")
            return render_template("importar.html", propiedades=propiedades, paso=2, token=token,
                                   encabezados=encabezados, mapa=mapa, no_detectadas=[c for c in importador.REQUERIDAS if c not in mapa],
                                   etiquetas=importador.ETIQUETAS, campos=list(importador.ETIQUETAS))
        pend["mapa"] = mapa
        _actualizar_pendiente(token, pend)

    filas = importador.leer_filas(pend["texto"])
    idx_anuncio = mapa.get("anuncio")
    anuncios = sorted({f[idx_anuncio].strip() for f in filas[1:]
                       if idx_anuncio is not None and idx_anuncio < len(f) and f[idx_anuncio].strip()})

    if request.method == "POST" and "asignar" in request.form:
        ids_validos = {p["id"] for p in propiedades}
        propiedad_map, creadas = {}, []
        idx_mon = mapa.get("moneda")
        for i, anuncio in enumerate(anuncios):   # por número: nombres raros ya no se pierden
            valor = request.form.get(f"prop_{i}") or ""
            if valor == "nueva":
                # ### CAMBIO AQUÍ ### crea la propiedad con el nombre del anuncio de Airbnb
                mon = next((importador._moneda(f[idx_mon]) for f in filas[1:]
                            if idx_mon is not None and idx_mon < len(f) and idx_anuncio < len(f)
                            and f[idx_anuncio].strip() == anuncio), "") if idx_mon is not None else ""
                pid = db.execute("""INSERT INTO propiedades (nombre, barrio, ciudad, provincia, pais, pais_codigo, tipo, estado, moneda)
                                    VALUES (%s, '', 'Buenos Aires', 'Ciudad Autónoma de Buenos Aires', 'Argentina', 'AR',
                                            'depto', 'activa', %s) RETURNING id""",
                                 (anuncio[:120], mon if mon in ("ARS", "USD") else "ARS"))
                propiedad_map[anuncio] = pid
                creadas.append(anuncio)
                continue
            pid = int(valor) if valor.isdigit() else None
            if pid in ids_validos:
                propiedad_map[anuncio] = pid
        if not propiedad_map:
            flash("Elegí a qué propiedad corresponde al menos un anuncio.", "error")
            return redirect(url_for("importar_asignar", t=token))
        recordados = _anuncios_recordados()
        recordados.update(propiedad_map)
        db.execute("""INSERT INTO config (clave, valor) VALUES ('anuncio_map', %s)
                      ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor""", (json.dumps(recordados, ensure_ascii=False),))

        filas_ok, omitidas, movimientos = importador.procesar_csv(pend["texto"], mapa, propiedad_map)
        foto_antes, movs_antes = novedades.antes_de_importar({f["codigo_confirmacion"] for f in filas_ok})   # ### CAMBIO AQUÍ ###
        mon_prop = {p["id"]: (p.get("moneda") or "ARS") for p in propiedades}
        for fila in filas_ok:   # si el CSV no trae moneda, se usa la de la propiedad
            fila["moneda"] = fila.get("moneda") or mon_prop.get(fila["propiedad_id"], "ARS")

        # "Ganancias" trae los montos exactos; "Reservas" un monto aproximado que no pisa los exactos
        solo_completar = importador.tipo_de_archivo(encabezados) == "reservas"
        importadas = actualizadas = 0
        for fila in filas_ok:
            try:
                nueva = db.execute("""
                    INSERT INTO reservas
                    (propiedad_id,codigo_confirmacion,fecha_inicio,fecha_fin,noches,
                     ingreso_bruto,comision_airbnb,limpieza,ingreso_neto,anticipacion_dias,
                     huesped_nombre,estado,moneda,fecha_reserva)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (codigo_confirmacion) DO UPDATE SET
                      huesped_nombre = COALESCE(NULLIF(EXCLUDED.huesped_nombre,''), reservas.huesped_nombre),
                      estado = CASE WHEN EXCLUDED.estado = 'completada' AND reservas.estado = 'cancelada'
                                    THEN reservas.estado ELSE EXCLUDED.estado END,
                      -- ### CAMBIO AQUÍ ### archivo de Reservas: si la reserva ya tiene cobros reales (Ganancias) no se tocan;
                      -- si no, se actualiza con lo último de Airbnb (cambio de fechas/precio, o 0 si se canceló)
                      ingreso_bruto = CASE WHEN %s THEN (CASE WHEN EXISTS (SELECT 1 FROM movimientos_airbnb m WHERE m.codigo = reservas.codigo_confirmacion)
                                             THEN reservas.ingreso_bruto ELSE EXCLUDED.ingreso_bruto END)
                                             WHEN EXCLUDED.ingreso_bruto <> 0 THEN EXCLUDED.ingreso_bruto ELSE reservas.ingreso_bruto END,
                      comision_airbnb = CASE WHEN %s THEN (CASE WHEN EXISTS (SELECT 1 FROM movimientos_airbnb m WHERE m.codigo = reservas.codigo_confirmacion)
                                             THEN reservas.comision_airbnb ELSE EXCLUDED.comision_airbnb END)
                                             WHEN EXCLUDED.comision_airbnb <> 0 THEN EXCLUDED.comision_airbnb ELSE reservas.comision_airbnb END,
                      limpieza = CASE WHEN %s THEN (CASE WHEN EXISTS (SELECT 1 FROM movimientos_airbnb m WHERE m.codigo = reservas.codigo_confirmacion)
                                             THEN reservas.limpieza ELSE EXCLUDED.limpieza END)
                                             WHEN EXCLUDED.limpieza <> 0 THEN EXCLUDED.limpieza ELSE reservas.limpieza END,
                      ingreso_neto = CASE WHEN %s THEN (CASE WHEN EXISTS (SELECT 1 FROM movimientos_airbnb m WHERE m.codigo = reservas.codigo_confirmacion)
                                             THEN reservas.ingreso_neto ELSE EXCLUDED.ingreso_neto END)
                                             WHEN EXCLUDED.ingreso_neto <> 0 THEN EXCLUDED.ingreso_neto ELSE reservas.ingreso_neto END,
                      anticipacion_dias = COALESCE(EXCLUDED.anticipacion_dias, reservas.anticipacion_dias),
                      fecha_reserva = COALESCE(EXCLUDED.fecha_reserva, reservas.fecha_reserva),
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
                    fila.get("fecha_reserva"),
                    solo_completar, solo_completar, solo_completar, solo_completar
                ))
                if nueva:
                    importadas += 1
                else:
                    actualizadas += 1
            except Exception as e:
                print(f"[importar] {fila['codigo_confirmacion']}: {e}")
                omitidas.append({"fila": "—", "clase": "error",
                                 "motivo": f"No se pudo guardar {fila['codigo_confirmacion']} ({type(e).__name__})"})

        # cada cobro se guarda una sola vez; el monto de la reserva = suma de sus cobros
        if movimientos:
            db.execute_many("""
                INSERT INTO movimientos_airbnb (codigo, fecha, tipo, bruto, neto, comision, limpieza)
                VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING
            """, [(m["codigo"], m["fecha"], m["tipo"], round(m["bruto"], 2), round(m["neto"], 2),
                   round(m["comision"], 2), round(m["limpieza"], 2)) for m in movimientos])
            db.execute("""
                UPDATE reservas r SET ingreso_bruto = m.b, ingreso_neto = m.n,
                       comision_airbnb = CASE WHEN m.c <> 0 THEN m.c ELSE r.comision_airbnb END,
                       limpieza = CASE WHEN m.l <> 0 THEN m.l ELSE r.limpieza END
                FROM (SELECT codigo, SUM(bruto) b, SUM(neto) n, SUM(comision) c, SUM(limpieza) l
                      FROM movimientos_airbnb WHERE codigo = ANY(%s) GROUP BY codigo) m
                WHERE r.codigo_confirmacion = m.codigo
            """, (list({m["codigo"] for m in movimientos}),))

        try:   # ### CAMBIO AQUÍ ### anota las novedades (si falla, la importación igual quedó hecha)
            novedades.despues_de_importar(foto_antes, movs_antes, filas_ok, movimientos)
        except Exception as e:
            print(f"[novedades] {e}")
        _borrar_pendiente(token)
        if importadas or actualizadas:   # ### CAMBIO AQUÍ ### se anota la fecha para el aviso de la próxima carga
            db.execute("""INSERT INTO config (clave, valor) VALUES (%s, %s)
                          ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor""",
                       (f"ultima_importacion_{importador.tipo_de_archivo(encabezados)}", date.today().isoformat()))
        errores = [o for o in omitidas if o.get("clase") == "error"]
        ignoradas = [o for o in omitidas if o.get("clase") != "error"]
        if creadas:
            flash(f"Se crearon {len(creadas)} propiedad(es) con el nombre de Airbnb: {', '.join(creadas)}. "
                  f"Entrá a Propiedades y completá barrio, precio y costos (sin barrio no se busca la competencia).", "warn")
        flash(f"Importación completa: {importadas} reservas nuevas y {actualizadas} actualizadas"
              + (f", {len(ignoradas)} filas que no son reservas" if ignoradas else "")
              + (f", {len(errores)} filas con errores" if errores else "") + ".",
              "warn" if errores else "ok")
        session["import_resultado"] = {"importadas": importadas, "actualizadas": actualizadas,
                                       "errores": errores[:40], "ignoradas": ignoradas[:40],
                                       "n_errores": len(errores), "n_ignoradas": len(ignoradas)}
        return redirect(url_for("importar", resultado=1))

    recordados = _anuncios_recordados()
    return render_template("importar.html", propiedades=propiedades, paso=3, token=token,
                           anuncios=[(a, _sugerir_propiedad(a, propiedades, recordados)) for a in anuncios],
                           mapa=mapa, tipo_archivo=importador.tipo_de_archivo(encabezados))


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
        # ### CAMBIO AQUÍ ### precio con coma o puntos ("30.000", "45,50") y control de valores absurdos
        precio = importador.parsear_monto(f.get("precio_noche"))
        mon_c = f.get("moneda") if f.get("moneda") in monedas.MONEDAS else "ARS"
        lim = competencia_ia.TOPE_NOCHE.get(mon_c)
        if precio <= 0 or (lim and not (lim[0] <= precio <= lim[1])):
            rango = f" (entre {monedas.formatear(lim[0], mon_c)} y {monedas.formatear(lim[1], mon_c)})" if lim else ""
            flash(f"El precio por noche '{f.get('precio_noche')}' no parece válido{rango}. Revisá el número y la moneda.", "error")
            return redirect(url_for("competencia", pid=request.args.get("pid")))
        db.execute("""
            INSERT INTO competencia (barrio,tipo,ambientes,capacidad,precio_noche,fecha,fuente,notas,
                                     link,zona,origen,moneda,propiedad_id,plataforma,titulo)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'manual',%s,%s,%s,%s)
        """, (
            f.get("barrio"), f.get("tipo"),
            request.form.get("ambientes", type=int), request.form.get("capacidad", type=int),
            precio,
            (met.fecha_valida(f.get("fecha")) or date.today()).isoformat(), f.get("fuente",""), f.get("notas",""),
            _link_seguro(f.get("link","")), f.get("zona",""), mon_c,   # ### CAMBIO AQUÍ ### link validado
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
                           corrida_activa=competencia_auto.en_curso(),   # ### CAMBIO AQUÍ ###
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

    # ### CAMBIO AQUÍ ### si justo corre la búsqueda automática (o hubo doble toque), no se busca dos veces
    with db.bloqueo(competencia_auto.CLAVE_BLOQUEO) as libre:
        if not libre:
            flash("Ya se está actualizando la competencia. Esperá un par de minutos y recargá la página.", "warn")
            return redirect(url_for("competencia", pid=pid))
        res = competencia_ia.buscar_comparables(prop, monedas.tc_valor())   # ### CAMBIO AQUÍ ###
        if res["ok"]:
            competencia_auto.guardar_resultado(prop, res, monedas.tc_valor())
    if not res["ok"]:
        flash(res["error"], "error")
        return redirect(url_for("competencia", pid=pid))

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
    # ### CAMBIO AQUÍ ### el token de ejemplo de .env.example (es público) no sirve
    if token_ok in TOKENS_DE_EJEMPLO or len(token_ok or "") < 16:
        token_ok = None
    if not token_ok or not hmac.compare_digest(token, token_ok):
        return jsonify({"ok": False, "error": "No autorizado"}), 403
    competencia_auto.correr_en_segundo_plano()
    # ### CAMBIO AQUÍ ### también se leen los calendarios de Airbnb (en segundo plano)
    import threading
    threading.Thread(target=lambda: [_leer_calendario(p) for p in db.query("SELECT * FROM propiedades")], daemon=True).start()
    return jsonify({"ok": True, "mensaje": "Actualización de competencia iniciada."})


TOKENS_DE_EJEMPLO = {"inventar-una-clave-larga-y-secreta"}


@app.route("/salud")
def salud():
    """Para 'despertar' el servidor de Render antes de la tarea nocturna.
    ### CAMBIO AQUÍ ### /salud?db=1 además prueba la base (para el chequeo de salud de Render)."""
    if request.args.get("db"):
        try:
            db.query_one("SELECT 1 AS ok")
        except Exception:
            return "base de datos sin conexión", 503
    return "ok"


@app.route("/competencia/<int:cid>/eliminar", methods=["POST"])
@login_required
def eliminar_competencia(cid):
    borrado = db.execute("DELETE FROM competencia WHERE id=%s RETURNING id", (cid,))
    flash("Registro eliminado." if borrado else "Ese registro ya no existía.", "ok" if borrado else "warn")
    return redirect(url_for("competencia", pid=request.args.get("pid")))  # ### CAMBIO AQUÍ ###


# ════════════════════════════════════════════════════════════════════════════
# PRECIOS SUGERIDOS (ruta legacy — mantiene compatibilidad)
# ════════════════════════════════════════════════════════════════════════════

@app.route("/precios", methods=["GET","POST"])
@login_required
def precios():
    """### CAMBIO AQUÍ ### una sección plegable por propiedad con TODOS sus precios y costos.
    Adentro: calcular el precio de una fecha y cómo viene vendiendo."""
    import math
    from precio_estrategico import calcular_precio_estrategico

    pid_sel = request.values.get("propiedad_id", type=int)
    viejo = request.args.get("resaltar")
    if request.method == "GET" and pid_sel and viejo in ("ritmo", "mercado", "disposicion"):
        return redirect(url_for("precios", propiedad_id=pid_sel, resaltar=f"{viejo}-{pid_sel}"))
    propiedades = db.query("SELECT * FROM propiedades ORDER BY (COALESCE(estado,'activa') = 'inactiva'), nombre")
    if not pid_sel and propiedades:
        pid_sel = propiedades[0]["id"] if len(propiedades) == 1 else None
    fecha = (met.fecha_valida(request.values.get("fecha")) or date.today()).isoformat()
    hoy_d, tc = date.today(), monedas.tc_valor()
    reservas = db.query("SELECT * FROM reservas")
    try:
        lista_esp, _ = feriados.proximos(hoy_d, estrategia.DIAS_ADELANTE)
    except Exception:
        lista_esp = []
    fichas = []
    for p in propiedades:
        pid, mon = p["id"], p.get("moneda") or "ARS"
        mercado = None
        comps = competencia_auto.comparables_vigentes(pid, p.get("barrio"))
        st = competencia_ia.calcular_stats(comps, mon, tc) if comps else None
        if st:
            mercado = {"mediana": st["mediana"], "min": st["minimo"], "max": st["maximo"],
                       "rating_promedio_zona": st["rating"] or 4.5, "rating_real": bool(st["rating"]),
                       "cantidad_propiedades": st["cantidad"], "sin_convertir": st["sin_convertir"],
                       "fecha": max((c.get("fecha") or "") for c in comps)}
        try:
            a = estrategia.analizar(p, reservas, hoy_d, tc, lista_esp)
        except Exception as e:
            print(f"[precios] {pid}: {e}")
            a = None
        try:
            dispo = disposicion_pago.analizar(p, [r for r in reservas if r["propiedad_id"] == pid],
                                              mediana_mercado=mercado["mediana"] if mercado else None, tc=tc)
        except Exception as e:
            print(f"[disposicion] {e}")
            dispo = None
        fijos = {"Expensas": p.get("costo_expensas") or 0, "Servicios": p.get("costo_servicios") or 0,
                 "Limpieza (mensual)": p.get("costo_limpieza") or 0, "Comisión / otros": p.get("costo_comision") or 0}
        recambio = estrategia.recambio(p)
        proxima = None
        if a and a["precios"]:
            g = a["precios"][0]
            proxima = {"txt": g["txt"], "precio": g["precio"], "motivos": g["motivos"]}
        resultado = None
        if request.method == "POST" and pid == pid_sel:
            if not mercado:
                flash("Para calcular por fecha, primero buscá la competencia de esta propiedad en la sección Competencia.", "error")
            else:
                desde_90 = (hoy_d - timedelta(days=90)).isoformat()
                hist = [r for r in reservas if r["propiedad_id"] == pid and (r.get("estado") or "") != "cancelada"
                        and ((r.get("fecha_inicio") or "") >= desde_90 or (r.get("fecha_fin") or "") >= desde_90)]
                resultado = calcular_precio_estrategico(p, mercado, hist, fecha)
                costos = sum(fijos.values())
                paso_piso = 500 if costos / 30.44 >= 5000 else 1
                piso = math.ceil(costos / 30.44 * 1.15 / paso_piso) * paso_piso
                resultado["costo_noche"] = round(costos / 30.44)
                if piso > resultado["precio_minimo"]:
                    resultado["precio_minimo"] = piso
                    resultado["explicacion"] += (f" El mínimo se subió a {monedas.formatear(piso, mon)} para cubrir tus costos fijos.")
                    if resultado.get("precio_sugerido", 0) < piso:
                        resultado["precio_sugerido"] = piso
                    if resultado.get("precio_maximo", 0) <= resultado["precio_sugerido"]:
                        resultado["precio_maximo"] = math.ceil(resultado["precio_sugerido"] * 1.2 / paso_piso) * paso_piso
        fichas.append({"p": p, "mon": mon, "mercado": mercado, "a": a, "dispo": dispo, "fijos": fijos,
                       "fijos_total": sum(fijos.values()), "recambio": recambio, "proxima": proxima, "resultado": resultado,
                       "abierta": pid == pid_sel})
    return render_template("precios.html", fichas=fichas, fecha=fecha, propiedades=propiedades)


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
    pid, mensaje = None, ""

    # ### CAMBIO AQUÍ ### después de generar, la página se recarga con ?c=<id>: así "actualizar" o
    # "atrás" no vuelve a mandar la consulta (antes la duplicaba y gastaba la IA otra vez)
    cid_ver = request.args.get("c", type=int)
    if cid_ver and request.method == "GET":
        c = db.query_one("SELECT respuesta, pendiente FROM consultas_huespedes WHERE id=%s", (cid_ver,))
        if c:
            respuesta, pendiente = c["respuesta"], bool(c["pendiente"])

    if request.method == "POST":
        pid     = request.form.get("propiedad_id", type=int)
        mensaje = request.form.get("mensaje","").strip()[:4000]

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
                    return redirect(url_for("asistente", tab="huespedes", c=cid))
                except Exception as e:
                    flash(f"No se pudo generar la respuesta: {e}", "error")
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
        resenas=resenas, chat_hist=chat_hist, mensaje_prev=mensaje, prop_prev=pid,
        tab="huespedes" if request.method == "POST" else request.args.get("tab", "negocio"))


# ### CAMBIO AQUÍ ### — responder a mano una consulta pendiente
@app.route("/asistente/consulta/<int:cid>/responder", methods=["POST"])
@login_required
def responder_consulta(cid):
    texto = request.form.get("respuesta", "").strip()
    if texto:
        db.execute("UPDATE consultas_huespedes SET respuesta=%s, pendiente=0 WHERE id=%s", (texto, cid))
        flash("Consulta marcada como respondida.", "ok")
    else:   # ### CAMBIO AQUÍ ### antes no pasaba nada y no avisaba
        flash("Escribí la respuesta antes de marcarla como respondida.", "error")
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
    if not prop:
        flash("La propiedad elegida no existe.", "error")
        return redirect(url_for("asistente", tab="resenas"))
    puntaje = f.get("puntaje", type=int)
    if puntaje is not None and not 1 <= puntaje <= 5:
        puntaje = None
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
    """, (pid, (f.get("huesped") or "").strip()[:120], puntaje, texto[:5000], borrador, date.today().isoformat()))
    if borrador:
        flash("Reseña guardada con una respuesta sugerida: revisala, copiala y marcala como respondida.", "ok")
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
    flash("Reseña eliminada.", "ok")
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
    hoy = date.today()
    # ### CAMBIO AQUÍ ### fechas validadas (vacías, mal escritas o invertidas)
    desde, hasta = _rango_fechas(request.form.get("desde"), request.form.get("hasta"), date(hoy.year, 1, 1), hoy)
    prop_id  = request.form.get("propiedad_id", None, type=int)

    # ### CAMBIO AQUÍ ### — informe en la moneda elegida
    vista, tc = moneda_vista(), monedas.tc_valor()
    reservas, sin_tc = monedas.convertir_reservas(db.query("SELECT * FROM reservas"), vista, tc)
    filtradas = met.filtrar_reservas(reservas, desde, hasta, prop_id)

    prop = db.query_one("SELECT * FROM propiedades WHERE id=%s", (prop_id,)) if prop_id else None
    costos_mes, unidades = _costos_y_unidades(prop_id, vista, tc, avisar=True)
    stats = met.calcular_metricas(filtradas, desde, hasta, costos_mes, unidades)
    if sin_tc:
        flash(f"{sin_tc} reservas están en otra moneda y sus montos no entraron en el informe: "
              f"cargá el tipo de cambio.", "warn")

    try:
        # ### CAMBIO AQUÍ ### compara la MISMA propiedad (antes comparaba contra todas)
        comparativas = met.comparar_periodos(reservas, desde, hasta, prop_id, unidades)
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
            periodo=f"{filtro_fecha(desde)} al {filtro_fecha(hasta)}"
        )
    except Exception as e:
        flash(f"Error al generar informe con IA: {e}", "error")
        return redirect(url_for("dashboard"))

    titulo = f"Informe {'- ' + prop['nombre'] if prop else 'General'} ({filtro_fecha(desde)} al {filtro_fecha(hasta)})"
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
