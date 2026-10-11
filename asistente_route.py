"""
asistente_route.py — Ruta del asistente de negocio IA para Palermitan Host
Asesor que conoce todas las propiedades, reservas y métricas de Adriano.
"""
from flask import Blueprint, request, jsonify, session
from functools import wraps
import json
import monedas   # ### CAMBIO AQUÍ ###
import privacidad   # ### CAMBIO AQUÍ ### los nombres de huéspedes no viajan a Groq
import ia
from groq import Groq
import os
from datetime import datetime, timedelta

asistente_bp = Blueprint("asistente", __name__)

MAX_HISTORIAL = 10  # turnos (user+assistant) a mantener

# ### CAMBIO AQUÍ ### — modelo configurable (llama3-8b-8192 fue dado de baja por Groq)
CHAT_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")


# ### CAMBIO AQUÍ ### — el chat no tenía login: cualquiera podía consultar los datos del negocio
def login_required_api(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return jsonify({"error": "No autenticado"}), 401
        return f(*args, **kwargs)
    return decorated


# ### CAMBIO AQUÍ ### — historial guardado en la base (en la cookie superaba 4 KB y cerraba la sesión)
def _cargar_historial():
    import database as _db
    row = _db.query_one("SELECT valor FROM config WHERE clave='historial_asistente'")
    try:
        return json.loads(row["valor"]) if row else []
    except Exception:
        return []


def _guardar_historial(historial):
    import database as _db
    _db.execute("""
        INSERT INTO config (clave, valor) VALUES ('historial_asistente', %s)
        ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor
    """, (json.dumps(historial, ensure_ascii=False),))


MAX_CARACTERES_HISTORIAL = 6000   # ### CAMBIO AQUÍ ### tope de la conversación que se manda a la IA


def _recortar(historial):
    """### CAMBIO AQUÍ ### se queda con los últimos turnos que entran en el tope (los pedidos muy grandes
    los rechaza Groq). Siempre empieza con un mensaje del usuario."""
    historial = historial[-(MAX_HISTORIAL * 2):]
    total, out = 0, []
    for m in reversed(historial):
        total += len(m.get("content") or "")
        if out and total > MAX_CARACTERES_HISTORIAL:
            break
        out.append(m)
    out.reverse()
    while out and out[0].get("role") != "user":
        out.pop(0)
    return out


def get_db():
    """Obtiene una conexión del pool de base de datos."""
    import database as _db_mod
    return _db_mod.get_db_connection()

def release_db(conn):
    """Devuelve la conexión al pool."""
    import database as _db_mod
    _db_mod._release(conn)


def build_context(db, alias=None, mencionados=()):
    """
    Construye el contexto completo del negocio para el sistema prompt.
    Incluye propiedades, reservas recientes, métricas y referencia de mercado.
    """
    cur = db.cursor()

    # ── Propiedades ──────────────────────────────────────────────────────────
    cur.execute("""
        SELECT id, nombre, tipo, barrio, ambientes, capacidad,
               COALESCE(ciudad, '') AS ciudad, m2, COALESCE(cochera, 0) AS cochera,
               precio_base, COALESCE(moneda, 'ARS') as moneda,
               COALESCE(descripcion, '') as descripcion,
               COALESCE(info_huespedes, '') as info_huespedes,
               rating, COALESCE(reviews_count, 0) as reviews_count,
               COALESCE(estado, 'activa') as estado
        FROM propiedades ORDER BY nombre
    """)
    propiedades = cur.fetchall()
    cols_prop = [d[0] for d in cur.description]

    # ── Últimas 100 reservas ─────────────────────────────────────────────────
    cur.execute("""
        SELECT r.id,
               r.codigo_confirmacion,
               COALESCE(r.huesped_nombre, '') as huesped_nombre,
               r.fecha_inicio, r.fecha_fin, r.noches,
               r.ingreso_neto as precio_total,
               COALESCE(r.estado, 'completada') as estado,
               COALESCE(r.canal, 'airbnb') as canal,
               COALESCE(r.notas, '') as notas,
               COALESCE(r.moneda, 'ARS') as moneda,
               p.nombre as propiedad_nombre
        FROM reservas r
        JOIN propiedades p ON r.propiedad_id = p.id
        ORDER BY r.fecha_inicio DESC
        LIMIT 100
    """)
    reservas = cur.fetchall()
    cols_res = [d[0] for d in cur.description]

    # ── Métricas globales ─────────────────────────────────────────────────────
    # ### CAMBIO AQUÍ ### — métricas separadas por moneda (antes sumaba pesos con dólares)
    cur.execute("""
        SELECT COALESCE(moneda, 'ARS'), COUNT(*), COALESCE(SUM(ingreso_neto), 0), COALESCE(SUM(noches), 0)
        FROM reservas WHERE COALESCE(estado, 'completada') != 'cancelada'
        GROUP BY COALESCE(moneda, 'ARS')
    """)
    por_moneda = cur.fetchall()
    tc = monedas.tc_valor()
    total_res = sum(r[1] for r in por_moneda)
    total_noches = sum(r[3] for r in por_moneda)
    lineas_ing = [f"  - En {m}: {n} reservas, ingreso neto {monedas.formatear(s, m)}" for m, n, s, _ in por_moneda]
    if tc and len(por_moneda) > 1:
        tot_ars = sum(monedas.convertir(s, m, "ARS", tc) for m, _, s, _ in por_moneda)
        lineas_ing.append(f"  - Total convertido: {monedas.formatear(tot_ars, 'ARS')} "
                          f"= {monedas.formatear(tot_ars / tc, 'USD')} (TC {tc:,.2f})")

    # ── Ocupación últimos 90 días ─────────────────────────────────────────────
    # ### CAMBIO AQUÍ ### noches realmente ocupadas ÷ (90 días × propiedades activas).
    # Antes contaba días de LLEGADA: una estadía de 10 noches valía 1 día.
    import metricas
    from datetime import date as _date
    cur.execute("SELECT propiedad_id, fecha_inicio, fecha_fin, noches, estado FROM reservas")
    _cols = [d[0] for d in cur.description]
    _todas = [dict(zip(_cols, r)) for r in cur.fetchall()]
    _hoy = _date.today()
    _activas = sum(1 for p in propiedades if (p[-1] or "activa") != "inactiva") or 1
    _m90 = metricas.calcular_metricas(metricas.filtrar_reservas(_todas, _hoy - timedelta(days=89), _hoy),
                                      _hoy - timedelta(days=89), _hoy, 0, _activas)
    noches_90 = _m90.get("noches_ocupadas", 0)
    ocup_90 = _m90.get("tasa_ocupacion", 0)
    _nombres = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                "septiembre", "octubre", "noviembre", "diciembre"]
    # ### CAMBIO AQUÍ ### las MISMAS temporadas que usa la sección Precios (antes decía otras)
    from precio_estrategico import TEMPORADA_MULTIPLICADORES as _TM
    temporadas_txt = ", ".join(f"{_nombres[m - 1]} {t.lower()} (×{str(x).replace('.', ',')})"
                               for m, (t, x) in sorted(_TM.items()))

    # ── Config: chat_huespedes activo? ───────────────────────────────────────
    # ### CAMBIO AQUÍ ### — mercado desde la tabla competencia, en la moneda de cada propiedad
    cur.execute("""
        SELECT p.nombre, COALESCE(p.moneda,'ARS'), c.precio_noche, COALESCE(c.moneda,'ARS'), c.rating, c.fecha
        FROM propiedades p JOIN competencia c ON c.propiedad_id = p.id
        WHERE c.precio_noche > 0
    """)
    comp_por_prop = {}
    for nombre, mon_p, precio, mon_c, rating, fecha in cur.fetchall():
        comp_por_prop.setdefault((nombre, mon_p), []).append(
            {"precio_noche": precio, "moneda": mon_c, "rating": rating, "fecha": fecha})

    cur.execute("SELECT valor FROM config WHERE clave='chat_huespedes'")
    row = cur.fetchone()
    chat_activo = (row[0] == '1') if row else False

    cur.close()

    # ── Armar texto de propiedades ───────────────────────────────────────────
    prop_lines = []
    for p in propiedades:
        pd = dict(zip(cols_prop, p))
        prop_lines.append(
            f"- [{pd['id']}] {pd['nombre']} | {pd['tipo']} | {pd['barrio']}, {pd['ciudad']} | "
            f"{pd['ambientes']} amb | cap: {pd['capacidad']} | "
            f"{(str(pd['m2']) + ' m² | ') if pd['m2'] else ''}{'con cochera | ' if pd['cochera'] else ''}"
            f"precio base: {monedas.formatear(pd['precio_base'] or 0, pd['moneda'])} | "
            f"rating: {pd['rating'] or 'N/A'} ({pd['reviews_count'] or 0} reseñas) | "
            f"estado: {pd['estado']}"
        )
        if pd.get("info_huespedes"):
            prop_lines.append(f"  Info para huéspedes: {pd['info_huespedes'][:200]}")

    # ── Armar texto de reservas recientes (últimas 20 para contexto) ─────────
    res_lines = []
    for r in reservas[:20]:
        rd = dict(zip(cols_res, r))
        res_lines.append(
            # ### CAMBIO AQUÍ ### alias en vez del nombre real
            f"- {rd['propiedad_nombre']} | {(alias or {}).get((rd['huesped_nombre'] or '').strip(), 'Huésped sin nombre')} | "
            f"{rd['fecha_inicio']} → {rd['fecha_fin']} ({rd['noches']} noches) | "
            f"{monedas.formatear(rd['precio_total'] or 0, rd['moneda'])} | {rd['estado']}"
        )

    # ### CAMBIO AQUÍ ### si Adriano nombró a un huésped, se agregan TODAS sus reservas (con alias)
    lineas_mencion = []
    nombres_mencion = [n for n, a in (alias or {}).items() if a in mencionados]
    if nombres_mencion:
        cur = db.cursor()   # ### CAMBIO AQUÍ ### el cursor anterior ya se cerró
        cur.execute("""
            SELECT r.huesped_nombre, p.nombre, r.fecha_inicio, r.fecha_fin, r.noches,
                   r.ingreso_neto, COALESCE(r.moneda,'ARS'), COALESCE(r.estado,'completada')
            FROM reservas r JOIN propiedades p ON r.propiedad_id = p.id
            WHERE TRIM(r.huesped_nombre) = ANY(%s) ORDER BY r.fecha_inicio
        """, (nombres_mencion,))
        for h, pn, fi, ff, n, monto, mon, est in cur.fetchall():
            lineas_mencion.append(f"- {alias.get((h or '').strip())} | {pn} | {fi} → {ff} ({n} noches) | "
                                  f"{monedas.formatear(monto or 0, mon)} | {est}")
        cur.close()

    import competencia_ia
    mercado_lineas = []
    for (nombre, mon_p), comps in comp_por_prop.items():
        st = competencia_ia.calcular_stats(comps, mon_p, tc)
        if st:
            mercado_lineas.append(
                f"- {nombre}: {st['cantidad']} anuncios similares, mediana {monedas.formatear(st['mediana'], mon_p)}/noche "
                f"(rango {monedas.formatear(st['minimo'], mon_p)} – {monedas.formatear(st['maximo'], mon_p)}), "
                f"búsqueda del {max(c['fecha'] or '' for c in comps)}")
    mercado_txt = "\n".join(mercado_lineas) or "Sin datos de competencia todavía (usar la sección Competencia)."

    system_prompt = f"""Eres el asistente de negocio de Adriano, propietario de Palermitan Host, 
una administración de alquileres temporarios (barrios: ver PROPIEDADES ACTIVAS).

Tu rol es ser su asesor ejecutivo: analizar datos, detectar oportunidades, generar recomendaciones 
estratégicas y responder con precisión usando los datos reales del negocio.

═══ PROPIEDADES ACTIVAS ({len(propiedades)}) ═══
{chr(10).join(prop_lines) or "Sin propiedades cargadas aún."}

═══ ÚLTIMAS 20 RESERVAS ═══
{chr(10).join(res_lines) or "Sin reservas cargadas aún."}

═══ RESERVAS DE LOS HUÉSPEDES QUE SE MENCIONAN ═══
{chr(10).join(lineas_mencion) or "Ninguno mencionado."}

═══ MÉTRICAS GLOBALES (Adriano cobra en pesos y en dólares) ═══
- Total reservas: {total_res}
- Ingresos por moneda:
{chr(10).join(lineas_ing) or "  - Sin ingresos cargados"}
- Tipo de cambio cargado: {f"{tc:,.2f} pesos por dólar" if tc else "no cargado"}
- Total noches alquiladas: {total_noches}
- Ocupación últimos 90 días: {noches_90} noches ocupadas ({str(ocup_90).replace(".", ",")}% de las noches disponibles de {_activas} propiedad(es) activa(s))

═══ COMPETENCIA (última búsqueda con IA, sección Competencia) ═══
{mercado_txt}
- Temporadas que usa el sistema para los precios: {temporadas_txt}

═══ INSTRUCCIONES ═══
- Responde siempre en español rioplatense, directo y profesional.
- Usa los datos reales del negocio en tus análisis.
- Si te piden un informe, estrúcturalo con secciones claras.
- Si detectas algo preocupante (ocupación baja, precio fuera de mercado), señálalo.
- Chat con huéspedes: {"ACTIVO" if chat_activo else "DESACTIVADO (próxima versión)"}.
- No inventes datos. Si algo no está en el sistema, dilo claramente.
- Los huéspedes aparecen como "Huésped #número" por privacidad. Nombralos SIEMPRE así,
  exactamente con ese formato (el sistema le muestra a Adriano el nombre real).
"""
    return system_prompt


@asistente_bp.route("/asistente/chat", methods=["POST"])
@login_required_api
def chat():
    """Endpoint del chat del asistente de negocio."""
    data = request.get_json(silent=True) or {}
    mensaje = (data.get("mensaje") or "").strip()
    if not mensaje:
        return jsonify({"error": "Mensaje vacío"}), 400

    db = get_db()
    # ### CAMBIO AQUÍ ### alias de huéspedes: el nombre real nunca sale del sistema
    alias = {}
    try:   # ### CAMBIO AQUÍ ### la conexión se devuelve SIEMPRE (antes, un error la dejaba tomada)
        try:
            cur = db.cursor()
            cur.execute("SELECT TRIM(huesped_nombre), MIN(id) FROM reservas "
                        "WHERE COALESCE(TRIM(huesped_nombre),'') <> '' GROUP BY TRIM(huesped_nombre)")
            alias = privacidad.armar_alias(cur.fetchall())
        except Exception as e:
            db.rollback()
            print(f"[asistente] Error armando alias: {e}")
        historial = _cargar_historial()
        historial.append({"role": "user", "content": mensaje[:4000]})
        historial = _recortar(historial)
        enviados, mencionados = [], set()
        for m in historial:
            txt, usados = privacidad.ocultar(m["content"], alias)
            enviados.append({"role": m["role"], "content": txt})
            mencionados |= usados
        try:
            system_prompt = build_context(db, alias, mencionados)
        except Exception as e:
            db.rollback()
            print(f"[asistente] Error construyendo contexto: {e}")
            system_prompt = (
                "Eres el asistente de negocio de Palermitan Host. "
                "Actualmente no puedo acceder a los datos del sistema, "
                "pero puedo ayudarte con preguntas generales."
            )
    finally:
        release_db(db)

    messages = [{"role": "system", "content": system_prompt}] + enviados   # ### CAMBIO AQUÍ ### sin nombres

    try:
        resp = ia.completar(messages, CHAT_MODEL, 3000, 0.4)   # ### CAMBIO AQUÍ ### con respaldo de modelo
        respuesta = privacidad.mostrar(ia.texto_respuesta(resp), alias)   # ### CAMBIO AQUÍ ### alias → nombre real
    except Exception as e:
        print(f"[asistente] Error Groq: {e}")
        # ### CAMBIO AQUÍ ### el error NO se guarda en la conversación (antes quedaba trabado el chat):
        # se muestra y se puede volver a preguntar
        return jsonify({"respuesta": "⚠ " + ia.explicar_error(e), "error": True})

    historial.append({"role": "assistant", "content": respuesta})
    _guardar_historial(_recortar(historial))

    return jsonify({
        "respuesta": respuesta,
        "automatica": False,
    })


@asistente_bp.route("/asistente/limpiar", methods=["POST"])
@login_required_api
def limpiar_historial():
    """Limpia el historial de conversación."""
    _guardar_historial([])
    return jsonify({"ok": True})
