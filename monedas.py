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
    """Devuelve dict {valor, tipo, fecha} o None si no hay tipo de cambio cargado."""
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
    return data


def traer_tc(tipo="bolsa"):
    """Trae la cotización de venta desde dolarapi.com. Lanza excepción si falla."""
    if tipo not in TIPOS_DOLAR:
        raise ValueError("Tipo de dólar inválido")
    r = requests.get(f"https://dolarapi.com/v1/dolares/{tipo}", timeout=10)
    r.raise_for_status()
    venta = float(r.json()["venta"])
    if venta <= 0:
        raise ValueError("Cotización inválida")
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
    simbolo = "US$" if moneda == "USD" else "$"
    signo = "-" if round(monto) < 0 else ""   # ### CAMBIO AQUÍ ### antes: "$ -253.236"
    return f"{signo}{simbolo} {abs(monto):,.0f}".replace(",", ".")


def convertir_reservas(reservas, vista, tc):
    """
    Copia las reservas con los montos pasados a la moneda 'vista'.
    Devuelve (lista_convertida, cantidad_sin_convertir).
    """
    out, sin_tc = [], 0
    for r in reservas:
        mon = r.get("moneda") or "ARS"
        if mon != vista and not tc:
            sin_tc += 1
            continue
        c = dict(r)
        for k in ("ingreso_bruto", "ingreso_neto", "comision_airbnb", "limpieza"):
            c[k] = convertir(r.get(k) or 0, mon, vista, tc)
        c["moneda"] = vista
        out.append(c)
    return out, sin_tc


def costos_mensuales(props, vista, tc):
    """Suma de costos fijos mensuales de las propiedades, en la moneda 'vista'."""
    total = 0.0
    for p in props:
        suma = sum((p.get(k) or 0) for k in
                   ("costo_expensas", "costo_servicios", "costo_limpieza", "costo_comision"))
        v = convertir(suma, p.get("moneda") or "ARS", vista, tc)
        total += v or 0
    return total
