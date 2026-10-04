# importador.py
# Parsea CSV exportados desde Airbnb (español e inglés).
# Detecta columnas automáticamente; si falta alguna, devuelve lista para mapeo manual.

import csv
import io
from datetime import datetime, date

ALIASES = {
    "codigo_confirmacion": [
        "código de confirmación","confirmation code","codigo de confirmacion","reservation code"
    ],
    "fecha_inicio": [
        "fecha de inicio","start date","check-in date","check-in","arrival date","fecha inicio"
    ],
    "fecha_fin": [
        "fecha de finalización","end date","check-out date","check-out","departure date",
        "fecha fin","fecha de finalizacion"
    ],
    "noches": ["noches","nights","número de noches","numero de noches","duration"],
    "anuncio": [
        "anuncio","listing","listing title","propiedad","nombre del anuncio","listing name","property"
    ],
    "ingreso_bruto": [
        "cantidad","amount","ingresos brutos","gross earnings","total","monto","total earnings","pago"
    ],
    "comision_airbnb": [
        "comisión de servicio de airbnb","airbnb service fee","host service fee",
        "comision airbnb","comisión airbnb","tarifa de servicio"
    ],
    "limpieza": ["tarifa de limpieza","cleaning fee","limpieza","cleaning"],
    "ingreso_neto": [
        "ingresos netos","net earnings","net income","neto","you earn","earnings","payout"
    ],
    "tipo": ["tipo","type","transaction type","tipo de transacción","tipo de transaccion"],
}


def _norm(t):
    return str(t).strip().lower()


def detectar_columnas(encabezados):
    enc = [_norm(h) for h in encabezados]
    mapa = {}
    for clave, posibles in ALIASES.items():
        for p in posibles:
            if p in enc:
                mapa[clave] = enc.index(p)
                break
    requeridas = {"codigo_confirmacion","fecha_inicio","anuncio","ingreso_bruto"}
    no_detectadas = [c for c in requeridas if c not in mapa]
    return mapa, no_detectadas


def parsear_monto(texto):
    if not texto:
        return 0.0
    limpio = str(texto).replace("$","").replace("€","").replace(" ","").replace("\xa0","")
    if "," in limpio and "." in limpio:
        limpio = limpio.replace(".","").replace(",",".")
    elif "," in limpio:
        limpio = limpio.replace(",",".")
    try:
        return float(limpio)
    except ValueError:
        return 0.0


def parsear_fecha(texto):
    if not texto:
        return None
    formatos = ["%Y-%m-%d","%d/%m/%Y","%m/%d/%Y","%d-%m-%Y","%Y/%m/%d",
                "%d %b %Y","%b %d, %Y","%Y-%m-%dT%H:%M:%S"]
    texto = str(texto).strip()
    for fmt in formatos:
        try:
            return datetime.strptime(texto, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def procesar_csv(contenido_bytes, mapa_columnas, propiedad_map):
    """
    contenido_bytes : bytes del CSV subido
    mapa_columnas   : { clave_interna: indice_columna }
    propiedad_map   : { nombre_anuncio_csv: propiedad_id }
    Devuelve (filas_ok, omitidas)
    """
    texto = contenido_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(texto))
    next(reader, [])  # saltar encabezados

    filas_ok, omitidas = [], []

    for num, fila in enumerate(reader, start=2):
        if not any(fila):
            continue

        def col(clave, default=""):
            idx = mapa_columnas.get(clave)
            if idx is None or idx >= len(fila):
                return default
            return fila[idx].strip()

        tipo = _norm(col("tipo","reserva"))
        if tipo and tipo not in ("reserva","reservation","payout","","completada","completed"):
            omitidas.append({"fila": num, "motivo": f"Tipo ignorado: '{tipo}'"})
            continue

        codigo = col("codigo_confirmacion")
        if not codigo:
            omitidas.append({"fila": num, "motivo": "Sin código de confirmación"})
            continue

        anuncio = col("anuncio")
        propiedad_id = propiedad_map.get(anuncio)
        if not propiedad_id:
            omitidas.append({"fila": num, "motivo": f"Anuncio '{anuncio}' sin asignar"})
            continue

        fecha_inicio = parsear_fecha(col("fecha_inicio"))
        fecha_fin    = parsear_fecha(col("fecha_fin"))

        try:
            noches = int(col("noches","0") or 0)
        except ValueError:
            noches = 0

        ingreso_bruto   = parsear_monto(col("ingreso_bruto"))
        comision_airbnb = parsear_monto(col("comision_airbnb"))
        limpieza        = parsear_monto(col("limpieza"))
        ingreso_neto    = parsear_monto(col("ingreso_neto"))
        if ingreso_neto == 0 and ingreso_bruto > 0:
            ingreso_neto = ingreso_bruto - comision_airbnb

        filas_ok.append({
            "propiedad_id":        propiedad_id,
            "codigo_confirmacion": codigo,
            "fecha_inicio":        fecha_inicio,
            "fecha_fin":           fecha_fin,
            "noches":              noches,
            "ingreso_bruto":       ingreso_bruto,
            "comision_airbnb":     comision_airbnb,
            "limpieza":            limpieza,
            "ingreso_neto":        ingreso_neto,
            "anticipacion_dias":   None,
        })

    return filas_ok, omitidas
