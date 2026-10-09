# importador.py
# Parsea CSV exportados desde Airbnb (español e inglés).
# Detecta columnas automáticamente; si falta alguna, devuelve lista para mapeo manual.

import csv
import re  # ### CAMBIO AQUÍ ###
import io
import unicodedata   # ### CAMBIO AQUÍ ###
from datetime import datetime, date

# ### CAMBIO AQUÍ ### — el ORDEN importa: se toma el primer alias que aparezca en el archivo.
# Export de Ganancias (Historial de transacciones): "Amount"/"Importe" es lo que cobra el anfitrión
# (NETO) y "Gross earnings"/"Ingresos brutos" es el BRUTO. Antes se tomaba "Amount" como bruto.
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
    "noches": ["noches","nights","número de noches","numero de noches","duration",
               "n.º de noches","nº de noches","# of nights","n.° de noches"],
    "anuncio": [
        "anuncio","listing","listing title","propiedad","nombre del anuncio","listing name","property"
    ],
    "ingreso_bruto": [
        "gross earnings","ingresos brutos","ganancias brutas","total earnings","ingresos totales",
        "cantidad","amount","importe","monto","total","pago","ingresos","earnings","ganancias"
    ],
    "comision_airbnb": [
        "comisión de servicio de airbnb","airbnb service fee","host service fee","service fee",
        "comision airbnb","comisión airbnb","tarifa de servicio","comisión de servicio","comision de servicio",
        "tarifa de servicio del anfitrión"
    ],
    "limpieza": ["tarifa de limpieza","cleaning fee","limpieza","cleaning"],
    "ingreso_neto": [
        "ingresos netos","net earnings","net income","neto","you earn",
        "amount","importe","cantidad","monto","earnings","ganancias","payout","paid out","pagado"
    ],
    "tipo": ["tipo","type","transaction type","tipo de transacción","tipo de transaccion"],
    # ### CAMBIO AQUÍ ### — columnas del export de "Reservas" de Airbnb (trae futuras, huésped y estado)
    "huesped_nombre": ["nombre del huésped","nombre del huesped","huésped","huesped","guest",
                       "guest name","nombre"],
    "estado": ["estado","status"],
    "fecha_reserva": ["reservada","fecha de reserva","fecha de la reserva","booked","booking date","reservado"],
    "moneda": ["moneda","currency"],   # ### CAMBIO AQUÍ ###
}


def _norm(t):
    # ### CAMBIO AQUÍ ### sin acentos, sin espacios dobles y sin "#"/"n.º" (Airbnb los cambia según idioma)
    t = unicodedata.normalize("NFD", str(t).strip().lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"^(#|n\.?\s*[oº°]\.?)\s*(of\s+|de\s+)?", "", t)
    return re.sub(r"\s+", " ", t).strip()


def _es_ingles(encabezados):
    enc = {_norm(h) for h in encabezados}
    return bool(enc & {"start date", "confirmation code", "listing", "nights", "end date", "guest"})


def detectar_columnas(encabezados):
    enc = [_norm(h) for h in encabezados]
    mapa, usadas = {}, set()
    for clave, posibles in ALIASES.items():
        for p in posibles:
            p = _norm(p)
            if p in enc:
                idx = enc.index(p)
                # bruto y neto pueden compartir columna (export de Reservas); el resto no
                if idx in usadas and clave not in ("ingreso_neto", "ingreso_bruto"):
                    continue
                mapa[clave] = idx
                usadas.add(idx)
                break
    requeridas = {"codigo_confirmacion","fecha_inicio","anuncio","ingreso_bruto"}
    no_detectadas = [c for c in requeridas if c not in mapa]
    return mapa, no_detectadas


def parsear_monto(texto):
    if not texto:
        return 0.0
    t = str(texto).strip().replace("\u2212", "-")   # signo menos unicode
    negativo = t.startswith("(") and t.endswith(")")  # (45.00) = negativo
    # ### CAMBIO AQUÍ ### se queda solo con números, separadores y signo ("US$ 1,234.56" daba 0)
    limpio = re.sub(r"[^0-9.,-]", "", t)
    if negativo and not limpio.startswith("-"):
        limpio = "-" + limpio
    # ### CAMBIO AQUÍ ### — el separador decimal es el ÚLTIMO que aparece.
    # Antes "45.000" daba 45 y "1,234.56" daba 1.23
    if "," in limpio and "." in limpio:
        if limpio.rfind(",") > limpio.rfind("."):
            limpio = limpio.replace(".","").replace(",",".")   # 1.234,56
        else:
            limpio = limpio.replace(",","")                    # 1,234.56
    elif re.fullmatch(r"-?\d{1,3}([.,]\d{3})+", limpio):
        limpio = limpio.replace(".","").replace(",","")        # 45.000 / 45,000
    elif "," in limpio:
        limpio = limpio.replace(",",".")                       # 45,5
    try:
        return float(limpio)
    except ValueError:
        return 0.0


def parsear_fecha(texto, orden="dmy"):
    """### CAMBIO AQUÍ ### orden: 'dmy' (día/mes, Airbnb en español) o 'mdy' (mes/día, Airbnb en inglés).
    Antes "10/05/2026" del export en inglés (5 de octubre) se leía como 10 de mayo."""
    if not texto:
        return None
    barra = ["%d/%m/%Y", "%m/%d/%Y"] if orden == "dmy" else ["%m/%d/%Y", "%d/%m/%Y"]
    formatos = ["%Y-%m-%d"] + barra + ["%d-%m-%Y","%Y/%m/%d","%d %b %Y","%b %d, %Y","%Y-%m-%dT%H:%M:%S",
                "%m/%d/%y" if orden == "mdy" else "%d/%m/%y"]
    texto = str(texto).strip()
    for fmt in formatos:
        try:
            return datetime.strptime(texto, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def detectar_orden_fechas(filas, indices, ingles):
    """Mira todas las fechas con barra del archivo: si alguna tiene el primer número > 12 es día/mes;
    si alguna tiene el segundo > 12 es mes/día. Si no se puede saber, según el idioma del archivo."""
    for fila in filas:
        for i in indices:
            if i is None or i >= len(fila):
                continue
            m = re.match(r"\s*(\d{1,2})/(\d{1,2})/\d{2,4}", fila[i] or "")
            if not m:
                continue
            a, b = int(m.group(1)), int(m.group(2))
            if a > 12 >= b:
                return "dmy"
            if b > 12 >= a:
                return "mdy"
    return "mdy" if ingles else "dmy"


def tipo_de_archivo(encabezados):
    """'ganancias' (Historial de transacciones: montos confiables) o 'reservas' (lista de reservas)."""
    enc = {_norm(h) for h in encabezados}
    claves = {_norm(x) for x in ("gross earnings", "ingresos brutos", "ganancias brutas", "service fee",
                                 "tarifa de servicio", "amount", "importe", "type", "tipo")}
    return "ganancias" if enc & claves else "reservas"


def _moneda(texto):
    t = (texto or "").strip().upper()
    if t in ("USD", "US$", "U$S", "DOLARES", "DÓLARES"):
        return "USD"
    if t in ("ARS", "$", "PESOS", "AR$"):
        return "ARS"
    return ""


def procesar_csv(contenido_bytes, mapa_columnas, propiedad_map):
    """
    contenido_bytes : bytes del CSV subido
    mapa_columnas   : { clave_interna: indice_columna }
    propiedad_map   : { nombre_anuncio_csv: propiedad_id }
    Devuelve (filas_ok, omitidas)
    """
    texto = contenido_bytes.decode("utf-8-sig", errors="replace")
    todas = list(csv.reader(io.StringIO(texto)))
    encabezados = todas[0] if todas else []
    # ### CAMBIO AQUÍ ### formato de fecha del archivo (día/mes o mes/día)
    orden = detectar_orden_fechas(todas[1:], [mapa_columnas.get(k) for k in ("fecha_inicio", "fecha_fin", "fecha_reserva")],
                                  _es_ingles(encabezados))

    filas_ok, omitidas = [], []
    por_codigo = {}   # ### CAMBIO AQUÍ ### estadías largas: Airbnb parte el pago en varias filas con el mismo código

    for num, fila in enumerate(todas[1:], start=2):
        if not any(fila):
            continue

        def col(clave, default=""):
            idx = mapa_columnas.get(clave)
            if idx is None or idx >= len(fila):
                return default
            return fila[idx].strip()

        tipo = _norm(col("tipo","reserva"))
        if tipo in ("payout", "pago", "transferencia"):
            continue   # ### CAMBIO AQUÍ ### filas de transferencia al banco: no son reservas (no se cuentan como error)
        if tipo and tipo not in ("reserva","reservation","","completada","completed"):
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

        fecha_inicio = parsear_fecha(col("fecha_inicio"), orden)
        fecha_fin    = parsear_fecha(col("fecha_fin"), orden)
        if not fecha_inicio:   # ### CAMBIO AQUÍ ### sin fecha la reserva no sirve para ninguna métrica
            omitidas.append({"fila": num, "motivo": f"Fecha de inicio inválida: '{col('fecha_inicio')}'"})
            continue

        try:
            noches = int(col("noches","0") or 0)
        except ValueError:
            noches = 0

        ingreso_bruto   = parsear_monto(col("ingreso_bruto"))
        comision_airbnb = parsear_monto(col("comision_airbnb"))
        limpieza        = parsear_monto(col("limpieza"))
        ingreso_neto    = parsear_monto(col("ingreso_neto"))
        if ingreso_neto == 0 and ingreso_bruto > 0:
            ingreso_neto = ingreso_bruto - abs(comision_airbnb)  # ### CAMBIO AQUÍ ### la comisión viene negativa

        # ### CAMBIO AQUÍ ### — huésped, estado y anticipación (días entre reserva y llegada)
        estado_txt = _norm(col("estado", ""))
        if "cancel" in estado_txt:
            estado = "cancelada"
        elif any(p in estado_txt for p in ("pendiente", "pending", "solicit", "request")):
            estado = "pendiente"
        elif any(p in estado_txt for p in ("past", "anterior", "complet", "finaliz")):
            estado = "completada"   # ### CAMBIO AQUÍ ### "Past guest" / "Huésped anterior"
        elif estado_txt:
            estado = "confirmada"
        else:
            estado = "completada"
        fecha_res = parsear_fecha(col("fecha_reserva"), orden)
        anticipacion = None
        if fecha_res and fecha_inicio:
            anticipacion = (datetime.strptime(fecha_inicio, "%Y-%m-%d") -
                            datetime.strptime(fecha_res, "%Y-%m-%d")).days

        nueva = {
            "propiedad_id":        propiedad_id,
            "codigo_confirmacion": codigo,
            "fecha_inicio":        fecha_inicio,
            "fecha_fin":           fecha_fin,
            "noches":              noches,
            "ingreso_bruto":       ingreso_bruto,
            "comision_airbnb":     comision_airbnb,
            "limpieza":            limpieza,
            "ingreso_neto":        ingreso_neto,
            "anticipacion_dias":   anticipacion,
            "huesped_nombre":      col("huesped_nombre"),
            "moneda":              _moneda(col("moneda")),   # ### CAMBIO AQUÍ ### vacío = moneda de la propiedad
            "estado":              estado,
        }
        # ### CAMBIO AQUÍ ### mismo código en varias filas → se suman los montos (no se pisa)
        prev = por_codigo.get(codigo)
        if prev:
            for k in ("ingreso_bruto", "comision_airbnb", "limpieza", "ingreso_neto"):
                prev[k] = round(prev[k] + nueva[k], 2)
            prev["noches"] = max(prev["noches"], nueva["noches"])
            prev["fecha_inicio"] = min(x for x in (prev["fecha_inicio"], nueva["fecha_inicio"]) if x)
            fines = [x for x in (prev["fecha_fin"], nueva["fecha_fin"]) if x]
            prev["fecha_fin"] = max(fines) if fines else None
            continue
        por_codigo[codigo] = nueva
        filas_ok.append(nueva)

    for f in filas_ok:   # noches que faltan: se calculan con las fechas
        if not f["noches"] and f["fecha_inicio"] and f["fecha_fin"]:
            f["noches"] = max((datetime.strptime(f["fecha_fin"], "%Y-%m-%d") -
                               datetime.strptime(f["fecha_inicio"], "%Y-%m-%d")).days, 0)
    return filas_ok, omitidas
