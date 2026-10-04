"""
asistente_route.py — Ruta del asistente de negocio IA para Palermitan Host
Asesor que conoce todas las propiedades, reservas y métricas de Adriano.
"""
from flask import Blueprint, request, jsonify, session
from groq import Groq
import os
from datetime import datetime, timedelta

asistente_bp = Blueprint("asistente", __name__)

MAX_HISTORIAL = 10  # turnos (user+assistant) a mantener en sesión


def get_db():
    """Import db connection from app context."""
    from database import get_db_connection
    return get_db_connection()


def build_context(db):
    """
    Construye el contexto completo del negocio para el sistema prompt.
    Incluye propiedades, reservas recientes, métricas y referencia de mercado.
    """
    cur = db.cursor()

    # ── Propiedades ──────────────────────────────────────────────────────────
    cur.execute("""
        SELECT id, nombre, tipo, barrio, ambientes, capacidad,
               precio_base, descripcion, info_huespedes,
               rating, reviews_count, estado
        FROM propiedades ORDER BY nombre
    """)
    propiedades = cur.fetchall()
    cols_prop = [d[0] for d in cur.description]

    # ── Últimas 100 reservas ─────────────────────────────────────────────────
    cur.execute("""
        SELECT r.id, r.codigo_airbnb, r.huesped_nombre,
               r.fecha_inicio, r.fecha_fin, r.noches,
               r.precio_total, r.estado, r.canal, r.notas,
               p.nombre as propiedad_nombre
        FROM reservas r
        JOIN propiedades p ON r.propiedad_id = p.id
        ORDER BY r.fecha_inicio DESC
        LIMIT 100
    """)
    reservas = cur.fetchall()
    cols_res = [d[0] for d in cur.description]

    # ── Métricas globales ─────────────────────────────────────────────────────
    cur.execute("""
        SELECT COUNT(*) as total_reservas,
               COALESCE(SUM(precio_total), 0) as ingresos_total,
               COALESCE(AVG(precio_total), 0) as ticket_promedio,
               COALESCE(SUM(noches), 0) as noches_total
        FROM reservas WHERE estado != 'cancelada'
    """)
    metricas = dict(zip([d[0] for d in cur.description], cur.fetchone()))

    # ── Ocupación últimos 90 días ─────────────────────────────────────────────
    cur.execute("""
        SELECT COUNT(DISTINCT DATE(fecha_inicio)) as dias_con_reserva
        FROM reservas
        WHERE fecha_inicio >= CURRENT_DATE - INTERVAL '90 days'
          AND estado != 'cancelada'
    """)
    row = cur.fetchone()
    dias_ocupados = row[0] if row else 0

    # ── Config: chat_huespedes activo? ───────────────────────────────────────
    cur.execute("SELECT valor FROM config WHERE clave='chat_huespedes'")
    row = cur.fetchone()
    chat_activo = (row[0] == '1') if row else False

    cur.close()

    # ── Armar texto de propiedades ───────────────────────────────────────────
    prop_lines = []
    for p in propiedades:
        pd = dict(zip(cols_prop, p))
        prop_lines.append(
            f"- [{pd['id']}] {pd['nombre']} | {pd['tipo']} | {pd['barrio']} | "
            f"{pd['ambientes']} amb | cap: {pd['capacidad']} | "
            f"precio base: ${pd['precio_base']:,} | "
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
            f"- {rd['propiedad_nombre']} | {rd['huesped_nombre']} | "
            f"{rd['fecha_inicio']} → {rd['fecha_fin']} ({rd['noches']} noches) | "
            f"${rd['precio_total']:,} | {rd['estado']}"
        )

    system_prompt = f"""Eres el asistente de negocio de Adriano, propietario de Palermitan Host, 
una inmobiliaria de alquileres temporarios en Palermo, Buenos Aires.

Tu rol es ser su asesor ejecutivo: analizar datos, detectar oportunidades, generar recomendaciones 
estratégicas y responder con precisión usando los datos reales del negocio.

═══ PROPIEDADES ACTIVAS ({len(propiedades)}) ═══
{chr(10).join(prop_lines) or "Sin propiedades cargadas aún."}

═══ ÚLTIMAS 20 RESERVAS ═══
{chr(10).join(res_lines) or "Sin reservas cargadas aún."}

═══ MÉTRICAS GLOBALES ═══
- Total reservas: {metricas['total_reservas']}
- Ingresos totales: ${metricas['ingresos_total']:,.0f}
- Ticket promedio: ${metricas['ticket_promedio']:,.0f}
- Total noches alquiladas: {metricas['noches_total']}
- Días con reservas (últimos 90): {dias_ocupados} de 90 ({dias_ocupados/90*100:.0f}%)

═══ REFERENCIA DE MERCADO — PALERMO ═══
- Departamento 1 amb: $18.000 – $35.000/noche (mediana ~$25.000)
- Departamento 2 amb: $25.000 – $50.000/noche (mediana ~$35.000)  
- Departamento 3+ amb: $35.000 – $70.000/noche (mediana ~$50.000)
- Rating promedio zona: 4.6/5.0
- Temporada alta: diciembre-enero, Carnaval; baja: junio-agosto

═══ INSTRUCCIONES ═══
- Responde siempre en español rioplatense, directo y profesional.
- Usa los datos reales del negocio en tus análisis.
- Si te piden un informe, estrúcturalo con secciones claras.
- Si detectas algo preocupante (ocupación baja, precio fuera de mercado), señálalo.
- Chat con huéspedes: {"ACTIVO" if chat_activo else "DESACTIVADO (próxima versión)"}.
- No inventes datos. Si algo no está en el sistema, dilo claramente.
"""
    return system_prompt


@asistente_bp.route("/asistente", methods=["GET"])
def asistente_page():
    from flask import render_template
    return render_template("asistente.html")


@asistente_bp.route("/asistente/chat", methods=["POST"])
def chat():
    """Endpoint del chat del asistente de negocio."""
    data = request.get_json()
    mensaje = (data.get("mensaje") or "").strip()
    if not mensaje:
        return jsonify({"error": "Mensaje vacío"}), 400

    db = get_db()
    try:
        system_prompt = build_context(db)
    except Exception as e:
        print(f"[asistente] Error construyendo contexto: {e}")
        system_prompt = (
            "Eres el asistente de negocio de Palermitan Host. "
            "Actualmente no puedo acceder a los datos del sistema, "
            "pero puedo ayudarte con preguntas generales."
        )
    finally:
        db.close()

    # ── Historial de sesión ──────────────────────────────────────────────────
    if "historial_asistente" not in session:
        session["historial_asistente"] = []

    historial = session["historial_asistente"]
    historial.append({"role": "user", "content": mensaje})

    # Mantener solo los últimos MAX_HISTORIAL turnos
    if len(historial) > MAX_HISTORIAL * 2:
        historial = historial[-(MAX_HISTORIAL * 2):]

    messages = [{"role": "system", "content": system_prompt}] + historial

    try:
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        resp = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=messages,
            max_tokens=1024,
            temperature=0.4,
        )
        respuesta = resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[asistente] Error Groq: {e}")
        respuesta = "Error al conectar con el servicio de IA. Verificá la API key en las variables de entorno."

    historial.append({"role": "assistant", "content": respuesta})
    session["historial_asistente"] = historial
    session.modified = True

    return jsonify({
        "respuesta": respuesta,
        "automatica": False,
    })


@asistente_bp.route("/asistente/limpiar", methods=["POST"])
def limpiar_historial():
    """Limpia el historial de conversación."""
    session.pop("historial_asistente", None)
    return jsonify({"ok": True})
