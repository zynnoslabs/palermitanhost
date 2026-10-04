"""
ruta_precios.py — Rutas de análisis de precios y cálculo estratégico
"""
from flask import Blueprint, request, jsonify, render_template
from datetime import datetime
import json

precios_bp = Blueprint("precios", __name__)


def get_db():
    from database import get_db_connection
    return get_db_connection()


@precios_bp.route("/precios")
def precios_page():
    return render_template("precios.html")


@precios_bp.route("/precios/calcular", methods=["POST"])
def calcular():
    """Scraping de mercado + cálculo estratégico para una propiedad."""
    data = request.get_json()
    propiedad_id = data.get("propiedad_id")
    fecha_str = data.get("fecha")
    noches = int(data.get("noches", 2))

    db = get_db()
    cur = db.cursor()

    # Obtener propiedad
    cur.execute("""
        SELECT id, nombre, tipo, barrio, ambientes, precio_base, rating, reviews_count
        FROM propiedades WHERE id = %s
    """, (propiedad_id,))
    prop_row = cur.fetchone()
    if not prop_row:
        cur.close()
        db.close()
        return jsonify({"error": "Propiedad no encontrada"}), 404

    cols = ["id", "nombre", "tipo", "barrio", "ambientes", "precio_base", "rating", "reviews_count"]
    propiedad = dict(zip(cols, prop_row))

    # Reservas históricas para cálculo de ocupación
    cur.execute("""
        SELECT fecha_inicio, fecha_fin FROM reservas
        WHERE propiedad_id = %s AND estado != 'cancelada'
          AND fecha_inicio >= CURRENT_DATE - INTERVAL '90 days'
    """, (propiedad_id,))
    reservas_hist = [{"fecha_inicio": str(r[0]), "fecha_fin": str(r[1])} for r in cur.fetchall()]

    cur.close()
    db.close()

    # Scraping de mercado
    from scraper import scrape_precios_zona
    fecha = datetime.fromisoformat(fecha_str) if fecha_str else datetime.now()
    mercado = scrape_precios_zona(
        barrio=propiedad["barrio"] or "Palermo",
        tipo_vivienda=propiedad["tipo"] or "departamento",
        ambientes=propiedad["ambientes"] or 1,
        fecha_desde=fecha,
        noches=noches,
    )

    # Cálculo estratégico
    from precio_estrategico import calcular_precio_estrategico
    resultado = calcular_precio_estrategico(propiedad, mercado, reservas_hist, fecha)

    # Combinar resultado con datos de mercado
    resultado["mercado"] = mercado

    # Cachear en config table
    _cachear(propiedad_id, resultado)

    return jsonify(resultado)


@precios_bp.route("/precios/mercado/<int:propiedad_id>")
def mercado_cacheado(propiedad_id):
    """Devuelve el último análisis cacheado para una propiedad."""
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT valor FROM config WHERE clave = %s", (f"precio_cache_{propiedad_id}",))
    row = cur.fetchone()
    cur.close()
    db.close()

    if not row:
        return jsonify({"error": "Sin datos cacheados"}), 404

    try:
        return jsonify(json.loads(row[0]))
    except Exception:
        return jsonify({"error": "Error al leer cache"}), 500


def _cachear(propiedad_id, resultado):
    """Guarda el resultado en la tabla config como cache."""
    try:
        db = get_db()
        cur = db.cursor()
        clave = f"precio_cache_{propiedad_id}"
        valor = json.dumps(resultado, default=str)
        cur.execute("""
            INSERT INTO config (clave, valor) VALUES (%s, %s)
            ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor
        """, (clave, valor))
        db.commit()
        cur.close()
        db.close()
    except Exception as e:
        print(f"[precios] Error cacheando: {e}")
