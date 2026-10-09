# monedas.py
# ### CAMBIO AQUÍ ### — Archivo nuevo: manejo de pesos (ARS) y dólares (USD).
#
# Cómo funciona:
#  - Cada propiedad tiene su moneda (precio base y costos en esa moneda).
#  - Cada reserva y cada anuncio de competencia guarda su propia moneda.
#  - Hay un tipo de cambio (USD -> ARS) guardado en la base. Se puede cargar a mano
#    o traer de dolarapi.com (oficial, blue, MEP, CCL o tarjeta).
#  - El usuario elige "ver en ARS" o "ver en USD" y los totales se convierten.

import json
import os
from datetime import date

import requests

import database as db

MONEDAS = ("ARS", "USD")
TIPOS_DOLAR = {
    "bolsa": "MEP",
    "blue": "Blue",
    "oficial": "Oficial",
    "contadoconliqui": "CCL",
    "tarjeta": "Tarjeta",
}


def normalizar(texto, default=None):
    """'US$', 'usd', 'Dólares' -> 'USD' ; '$', 'ars', 'pesos' -> 'ARS'."""
    t = (texto or "").strip().upper().replace("Ó", "O")
    if t in ("USD", "US$", "U$S", "U$D", "DOLAR", "DOLARES", "US DOLLAR"):
        return "USD"
    if t in ("ARS", "$", "AR$", "PESO", "PESOS", "ARG"):
        return "ARS"
    return default


def get_tc():
    """Devuelve dict {valor, tipo, fecha} o None si no hay tipo de cambio cargado.
    ### CAMBIO AQUÍ ### se lee una sola vez por página (antes, una consulta a la base por cada monto mostrado)."""
    try:
        from flask import g, has_app_context
        if has_app_context():
            if "_tc" not in g:
                g._tc = _leer_tc()
            return g._tc
    except Exception:
        pass
    return _leer_tc()


def _leer_tc():
    try:
        row = db.query_one("SELECT valor FROM config WHERE clave='tipo_cambio'")
        if row and row["valor"]:
            data = json.loads(row["valor"])
            if float(data.get("valor") or 0) > 0:
                return data
    except Exception:
        pass
    try:
        v = float(os.getenv("TIPO_CAMBIO_USD", "") or 0)
        if v > 0:
            return {"valor": v, "tipo": "variable de entorno", "fecha": ""}
    except ValueError:
        pass
    return None


def tc_valor():
    tc = get_tc()
    return float(tc["valor"]) if tc else None


def guardar_tc(valor, tipo="manual", fecha=None):
    data = {"valor": float(valor), "tipo": tipo, "fecha": fecha or date.today().isoformat()}
    db.execute("""
        INSERT INTO config (clave, valor) VALUES ('tipo_cambio', %s)
        ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor
    """, (json.dumps(data),))
    try:
        from flask import g, has_app_context
        if has_app_context():
            g.pop("_tc", None)
    except Exception:
        pass
    return data


def traer_tc(tipo="bolsa"):
    """Trae la cotización de venta desde dolarapi.com. Lanza excepción si falla."""
    if tipo not in TIPOS_DOLAR:
        raise ValueError("Tipo de dólar inválido")
    # ### CAMBIO AQUÍ ### mensajes claros si dolarapi.com no responde (antes mostraba el error técnico)
    try:
        r = requests.get(f"https://dolarapi.com/v1/dolares/{tipo}", timeout=10)
        r.raise_for_status()
        venta = float(r.json().get("venta") or 0)
    except Exception:
        raise ValueError("no se pudo conectar con dolarapi.com. Probá en un rato o cargalo a mano.")
    if venta <= 0:
        raise ValueError("dolarapi.com no devolvió una cotización válida. Cargalo a mano.")
    return guardar_tc(venta, f"Dólar {TIPOS_DOLAR[tipo]} (dolarapi.com)")


def convertir(monto, de, a, tc=None):
    """Convierte entre ARS y USD. Devuelve None si hace falta tipo de cambio y no hay."""
    if monto is None:
        return None
    de = de or "ARS"
    a = a or "ARS"
    if de == a:
        return float(monto)
    if not tc:
        return None
    return float(monto) * tc if de == "USD" else float(monto) / tc


def formatear(monto, moneda):
    if monto is None:
        return "—"
    from decimal import Decimal, ROUND_HALF_UP
    simbolo = "US$" if moneda == "USD" else "$"
    # ### CAMBIO AQUÍ ### redondeo comercial (2,5 → 3; antes daba 2) y signo adelante ("-$ 253.236")
    entero = int(Decimal(str(float(monto))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    signo = "-" if entero < 0 else ""
    return f"{signo}{simbolo} {abs(entero):,}".replace(",", ".")


def convertir_reservas(reservas, vista, tc):
    """
    Copia las reservas con los montos pasados a la moneda 'vista'.
    Devuelve (lista_convertida, cantidad_sin_convertir).
    """
    out, sin_tc = [], 0
    for r in reservas:
        mon = r.get("moneda") or "ARS"
        c = dict(r)
        if mon != vista and not tc:
            # ### CAMBIO AQUÍ ### sin tipo de cambio la reserva SIGUE contando noches y ocupación;
            # solo sus montos quedan afuera (antes se perdía la reserva entera)
            sin_tc += 1
            for k in ("ingreso_bruto", "ingreso_neto", "comision_airbnb", "limpieza"):
                c[k] = 0
            c["moneda"] = vista
            out.append(c)
            continue
        for k in ("ingreso_bruto", "ingreso_neto", "comision_airbnb", "limpieza"):
            c[k] = convertir(r.get(k) or 0, mon, vista, tc)
        c["moneda"] = vista
        out.append(c)
    return out, sin_tc


def costos_mensuales(props, vista, tc, faltantes=None):
    """Suma de costos fijos mensuales de las propiedades, en la moneda 'vista'.
    ### CAMBIO AQUÍ ### si se pasa una lista en 'faltantes', anota las propiedades que no se pudieron convertir."""
    total = 0.0
    for p in props:
        suma = sum((p.get(k) or 0) for k in
                   ("costo_expensas", "costo_servicios", "costo_limpieza", "costo_comision"))
        v = convertir(suma, p.get("moneda") or "ARS", vista, tc)
        if v is None and suma and faltantes is not None:
            faltantes.append(p.get("nombre") or "")
        total += v or 0
    return total
