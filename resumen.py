"""### CAMBIO AQUÍ ### RESUMEN DIARIO POR MAIL y REPORTE MENSUAL.

Resumen diario (lo manda la tarea programada de las 9 h, ver /tareas/resumen):
  · llegadas, salidas y limpiezas de hoy
  · las tareas de "Qué hacer hoy" con la plata en juego
Reporte mensual (el día 1, junto con el resumen, y en la página "Reporte del mes"):
  · ingresos, noches y ocupación del mes contra el anterior
  · cuántas sugerencias se siguieron y cómo salieron las pruebas

Configuración del mail (variables de entorno en Render):
  SMTP_HOST   ej. smtp.gmail.com          SMTP_PORT  465 (SSL) o 587 (STARTTLS)
  SMTP_USER   la cuenta que manda         SMTP_PASS  en Gmail: "contraseña de aplicación" (no la normal)
  MAIL_PARA   a quién le llega (varios separados por coma)
  APP_URL     la dirección del sistema, para el botón "Abrir" (ej. https://palermitan.onrender.com)
"""
import calendar
import os
import smtplib
import ssl
from datetime import date, timedelta
from email.message import EmailMessage

import database as db
import metricas as met
import monedas
import limpiezas as limp

MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def configurado():
    return all(os.getenv(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "MAIL_PARA"))


def destinatarios():
    return [x.strip() for x in (os.getenv("MAIL_PARA") or "").split(",") if "@" in x]


def movimientos_hoy(hoy):
    """Llegadas y salidas de hoy (solo el nombre de pila del huésped)."""
    props = {p["id"]: p["nombre"] for p in db.query("SELECT id, nombre FROM propiedades")}
    llegan, salen = [], []
    for r in db.query("SELECT * FROM reservas WHERE COALESCE(estado,'') <> 'cancelada'"):
        fi, ff, n = met._rango(r)
        nombre = (r.get("huesped_nombre") or "Huésped").split(" ")[0]
        if fi == hoy:
            llegan.append({"prop": props.get(r["propiedad_id"], ""), "huesped": nombre, "noches": n})
        if ff == hoy:
            salen.append({"prop": props.get(r["propiedad_id"], ""), "huesped": nombre})
    return llegan, salen


def _mes_rango(anio, mes):
    return date(anio, mes, 1), date(anio, mes, calendar.monthrange(anio, mes)[1])


def reporte_mes(anio, mes, vista="ARS", tc=None):
    """Números del mes contra el mes anterior, sugerencias seguidas y resultado de las pruebas."""
    import pruebas as prb
    d1, d2 = _mes_rango(anio, mes)
    a0 = date(anio, mes, 1) - timedelta(days=1)
    p1, p2 = _mes_rango(a0.year, a0.month)
    props = db.query("SELECT * FROM propiedades WHERE COALESCE(estado,'activa') <> 'inactiva'")
    unidades = len(props) or 1
    reservas, sin_tc = monedas.convertir_reservas(db.query("SELECT * FROM reservas"), vista, tc)
    este = met.calcular_metricas(reservas, d1.isoformat(), d2.isoformat(), 0, unidades) or {}
    antes = met.calcular_metricas(reservas, p1.isoformat(), p2.isoformat(), 0, unidades) or {}

    def var(k):
        a, b = este.get(k) or 0, antes.get(k) or 0
        return None if not b else round((a / b - 1) * 100)

    hechas = db.query_one("SELECT COUNT(*) n FROM acciones_estado WHERE estado='hecho' AND fecha BETWEEN %s AND %s",
                          (d1.isoformat(), d2.isoformat()))["n"]
    try:
        evaluadas = [p for p in prb.evaluar_todas(d2 + timedelta(days=1), tc) if d1.isoformat() <= (p.get("fecha") or "") <= d2.isoformat()]
    except Exception:
        evaluadas = []
    bien = sum(1 for p in evaluadas if p.get("codigo") in ("rapido", "ok"))
    mal = sum(1 for p in evaluadas if p.get("codigo") == "no")
    return {"titulo": f"{MESES[mes]} {anio}", "anterior": f"{MESES[a0.month]} {a0.year}", "vista": vista,
            "ingreso": este.get("ingreso_neto") or 0, "ingreso_var": var("ingreso_neto"),
            "noches": este.get("noches_ocupadas") or 0, "noches_var": var("noches_ocupadas"),
            "ocupacion": este.get("tasa_ocupacion") or 0, "ocupacion_antes": antes.get("tasa_ocupacion") or 0,
            "adr": este.get("adr") or 0, "reservas": este.get("total_reservas") or 0,
            "hechas": hechas, "pruebas": len(evaluadas), "pruebas_bien": bien, "pruebas_mal": mal,
            "sin_tc": sin_tc}


def datos_resumen(hoy, hoy_armado, vista="ARS", tc=None, mensual=False):
    llegan, salen = movimientos_hoy(hoy)
    limpias = [x for x in limp.proximas(hoy, 0) if x["fecha"] == hoy]
    tareas = []
    for b in hoy_armado["bloques"]:
        for x in b["acciones"]:
            if x["cuando"] == "hoy" and not x.get("cfg"):
                tareas.append({"prop": b["prop"]["nombre"], "titulo": x["titulo"], "hacer": x["hacer"],
                               "impacto": monedas.formatear(x["impacto"]["monto"], x["impacto"]["mon"]) if x.get("impacto") else None,
                               "orden": x.get("orden", 0)})
    tareas.sort(key=lambda t: t["orden"])
    faltan = [p["nombre"] for p in (hoy_armado["puesta"] or {}).get("pasos", []) if not p["ok"]]
    out = {"fecha": f"{DIAS[hoy.weekday()]} {hoy.day} de {MESES[hoy.month]}", "llegan": llegan, "salen": salen,
           "limpiezas": limpias, "tareas": tareas, "juego_txt": hoy_armado["juego_txt"],
           "datos_viejos": hoy_armado["datos_viejos"], "faltan": faltan,
           "app_url": (os.getenv("APP_URL") or "").rstrip("/"), "mensual": None}
    if mensual:
        a0 = hoy.replace(day=1) - timedelta(days=1)
        out["mensual"] = reporte_mes(a0.year, a0.month, vista, tc)
    return out


def asunto(d):
    partes = []
    if d["llegan"]:
        partes.append(f"{len(d['llegan'])} llegada{'s' if len(d['llegan']) != 1 else ''}")
    if d["salen"]:
        partes.append(f"{len(d['salen'])} salida{'s' if len(d['salen']) != 1 else ''}")
    if d["tareas"]:
        partes.append(f"{len(d['tareas'])} tarea{'s' if len(d['tareas']) != 1 else ''}")
    base = "PalermitanHost · " + d["fecha"].capitalize()
    return base + (": " + ", ".join(partes) if partes else ": día tranquilo")


def enviar(asunto_txt, html, texto):
    """Manda el mail. Devuelve (ok, mensaje de error en castellano)."""
    if not configurado():
        return False, "Falta configurar el mail (SMTP_HOST, SMTP_USER, SMTP_PASS y MAIL_PARA en Render)."
    msg = EmailMessage()
    msg["Subject"] = asunto_txt
    msg["From"] = os.getenv("MAIL_DE") or os.getenv("SMTP_USER")
    msg["To"] = ", ".join(destinatarios())
    msg.set_content(texto)
    msg.add_alternative(html, subtype="html")
    host, puerto = os.getenv("SMTP_HOST"), int(os.getenv("SMTP_PORT") or 465)
    try:
        ctx = ssl.create_default_context()
        if puerto == 465:
            with smtplib.SMTP_SSL(host, puerto, context=ctx, timeout=20) as s:
                s.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASS"))
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, puerto, timeout=20) as s:
                s.starttls(context=ctx)
                s.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASS"))
                s.send_message(msg)
        return True, ""
    except smtplib.SMTPAuthenticationError:
        return False, "El servidor de mail rechazó el usuario o la contraseña. En Gmail hay que usar una 'contraseña de aplicación'."
    except Exception as e:
        return False, f"No se pudo mandar el mail: {type(e).__name__}."
