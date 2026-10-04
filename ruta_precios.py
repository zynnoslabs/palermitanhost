# ruta_precios.py
from flask import Blueprint, request, jsonify, session
from functools import wraps
import json
from datetime import date

import database as db
from scraper import scrape_precios_zona
from precio_estrategico import calcular_precio_estrategico

precios_bp = Blueprint("precios_bp", __name__)


def login_required_api(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return jsonify({"error": "No autenticado"}), 401
        return f(*args, **kwargs)
    return decorated


@precios_bp.route("/precios/calcular", methods=["POST"])
@login_required_api
def calcular_precio():
    """
    Calcula precio estratégico para una propiedad.
    Body JSON: { propiedad_id, fecha_desde, noches }
    """
    data = request.get_json(silent=True) or {}
    propiedad_id = data.get("propiedad_id")
    fecha_desde  = data.get("fecha_desde", date.today().isoformat())
    noches       = int(data.get("noches", 2))

    if not propiedad_id:
        return jsonify({"error": "Falta propiedad_id", "codigo": "ERR-PRC-001"}), 400

    prop = db.query_one("SELECT * FROM propiedades WHERE id=%s", (propiedad_id,))
    if not prop:
        return jsonify({"error": "Propiedad no encontrada", "codigo": "ERR-PRC-001"}), 404

    # ── Scraping con fallback a cache DB ────────────────────────────────────
    # ### CAMBIO AQUÍ ### — se pasan propiedad_id y db para el fallback a cache
    mercado = scrape_precios_zona(
        barrio        = prop.get("barrio", "Palermo"),
        tipo_vivienda = prop.get("tipo", "departamento"),
        ambientes     = prop.get("ambientes", 2),
        fecha_desde   = fecha_desde,
        noches        = noches,
        propiedad_id  = propiedad_id,
        db            = db,
    )

    # ── Precio estratégico ──────────────────────────────────────────────────
    reservas_hist = db.query(
        "SELECT * FROM reservas WHERE propiedad_id=%s ORDER BY fecha_inicio DESC LIMIT 100",
        (propiedad_id,)
    )
    resultado = calcular_precio_estrategico(prop, mercado, reservas_hist, fecha_desde)

    # ── Guardar cache en tabla config ───────────────────────────────────────
    clave = f"precio_cache_{propiedad_id}"
    payload = json.dumps({**mercado, **resultado}, default=str)
    try:
        db.execute("""
            INSERT INTO config (clave, valor) VALUES (%s, %s)
            ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor
        """, (clave, payload))
    except Exception:
        pass  # Si no existe la tabla config, no bloquea la respuesta

    # ── Incluir info de error de scraping en la respuesta ──────────────────
    respuesta = {**resultado, **mercado}
    if mercado.get("error_detalle"):
        respuesta["advertencia"] = mercado["error_detalle"]

    return jsonify(respuesta)


@precios_bp.route("/precios/mercado/<int:pid>")
@login_required_api
def mercado_cache(pid):
    """Devuelve el último resultado cacheado de mercado para una propiedad."""
    clave = f"precio_cache_{pid}"
    row = db.query_one("SELECT valor FROM config WHERE clave=%s", (clave,))
    if not row:
        return jsonify({"error": "Sin datos en caché", "codigo": "ERR-PRC-002"}), 404
    try:
        return jsonify(json.loads(row["valor"]))
    except Exception:
        return jsonify({"error": "Cache corrupto", "codigo": "ERR-PRC-002"}), 500
