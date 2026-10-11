# importador.py
# Parsea CSV exportados desde Airbnb (español e inglés).
# Detecta columnas automáticamente; si falta alguna, devuelve lista para mapeo manual.

import csv
import re  # ### CAMBIO AQUÍ ###
import io
import unicodedata   # ### CAMBIO AQUÍ ###
from datetime import datetime, date, timedelta

# ### CAMBIO AQUÍ ### — el ORDEN importa: se toma el primer alias que aparezca en el archivo.
# Export de Ganancias (Historial de transacciones): "Amount"/"Importe" es lo que cobra el anfitrión
# (NETO) y "Gross earnings"/"Ingresos brutos" es el BRUTO. Antes se tomaba "Amount" como bruto.
ALIASES = {
    "codigo_confirmacion": [
        "código de confirmación","confirmation code","codigo de confirmacion","reservation code",
        "código de reservación","codigo de reservacion","código de la reserva"
    ],
    "fecha_inicio": [
        "fecha de inicio","start date","check-in date","check-in","arrival date","fecha inicio",
        "fecha de llegada","llegada"
    ],
    "fecha_fin": [
        "fecha de finalización","end date","check-out date","check-out","departure date",
        "fecha fin","fecha de finalizacion","fecha de salida","salida"
    ],
    "noches": ["noches","nights","número de noches","numero de noches","duration",
               "n.º de noches","nº de noches","# of nights","n.° de noches","duración","duracion"],
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
        "tarifa de servicio del anfitrión","host fee","tarifa del anfitrión","tarifa del anfitrion"
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
    "fecha_movimiento": ["date", "fecha", "fecha del pago", "payout date"],   # fecha de cada cobro (Ganancias)
}

# ### CAMBIO AQUÍ ### nombres que ve Adriano en el paso de columnas (en vez de "codigo_confirmacion")
ETIQUETAS = {
    "codigo_confirmacion": "Código de confirmación", "fecha_inicio": "Fecha de llegada (check-in)",
    "fecha_fin": "Fecha de salida (check-out)", "noches": "Noches", "anuncio": "Anuncio / propiedad",
    "ingreso_bruto": "Monto total (bruto)", "comision_airbnb": "Comisión de Airbnb", "limpieza": "Tarifa de limpieza",
    "ingreso_neto": "Monto que cobrás (neto)", "tipo": "Tipo de movimiento", "huesped_nombre": "Huésped",
    "estado": "Estado", "fecha_reserva": "Fecha en que se reservó", "moneda": "Moneda",
    "fecha_movimiento": "Fecha del movimiento",
}
REQUERIDAS = ("codigo_confirmacion", "fecha_inicio", "anuncio", "ingreso_bruto")

MESES = {"jan": 1, "january": 1, "ene": 1, "enero": 1, "feb": 2, "february": 2, "febrero": 2,
         "mar": 3, "march": 3, "marzo": 3, "apr": 4, "april": 4, "abr": 4, "abril": 4,
         "may": 5, "mayo": 5, "jun": 6, "june": 6, "junio": 6, "jul": 7, "july": 7, "julio": 7,
         "aug": 8, "august": 8, "ago": 8, "agosto": 8, "sep": 9, "sept": 9, "september": 9,
         "septiembre": 9, "setiembre": 9, "oct": 10, "october": 10, "octubre": 10,
         "nov": 11, "november": 11, "noviembre": 11, "dec": 12, "december": 12, "dic": 12, "diciembre": 12}


def _norm(t):
    # ### CAMBIO AQUÍ ### sin acentos, sin espacios dobles y sin "#"/"n.º"/"nº" adelante
    # (Airbnb los cambia según idioma). Solo se quitan si van seguidos de espacio: "Noches" queda igual.
    t = unicodedata.normalize("NFD", str(t).strip().lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"^(#|n\.?\s?[º°]\.?|no\.)\s*(of\s+|de\s+)?", "", t)
    return re.sub(r"\s+", " ", t).strip()


# ════════════ ### CAMBIO AQUÍ ### LECTURA DEL ARCHIVO ════════════
class ArchivoInvalido(ValueError):
    pass


def decodificar(contenido_bytes):
    """Bytes del archivo → texto. Acepta UTF-8, UTF-16 y el formato de Excel en Windows (cp1252).
    Rechaza con un mensaje claro un Excel (.xlsx), un PDF u otro archivo que no sea CSV."""
    b = contenido_bytes or b""
    if not b.strip():
        raise ArchivoInvalido("El archivo está vacío.")
    if b[:2] == b"PK":
        raise ArchivoInvalido("Ese archivo es un Excel (.xlsx). Subí el CSV tal como lo descarga Airbnb, "
                              "o en Excel usá Guardar como → CSV.")
    if b[:4] == b"%PDF":
        raise ArchivoInvalido("Ese archivo es un PDF. Subí el CSV que descarga Airbnb (Exportar CSV).")
    if b[:2] in (b"\xff\xfe", b"\xfe\xff"):
        texto = b.decode("utf-16")
    else:
        try:
            texto = b.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = b.decode("cp1252", errors="replace")
    texto = texto.lstrip("﻿")
    if "\x00" in texto:
        raise ArchivoInvalido("El archivo no es un CSV de texto. Descargalo de nuevo desde Airbnb.")
    return texto


def separador(texto):
    """',' (Airbnb) o ';' (si se abrió y guardó con Excel en castellano) o tabulación."""
    primera = texto.split("\n", 1)[0]
    cuentas = {d: primera.count(d) for d in (",", ";", "\t")}
    mejor = max(cuentas, key=cuentas.get)
    return mejor if cuentas[mejor] > 0 else ","


def leer_filas(texto):
    """Lista de filas (listas). Lanza ArchivoInvalido si el CSV está roto."""
    try:
        filas = list(csv.reader(io.StringIO(texto), delimiter=separador(texto)))
    except csv.Error:
        raise ArchivoInvalido("No se pudo leer el archivo como CSV. Descargalo de nuevo desde Airbnb.")
    filas = [f for f in filas if any((c or "").strip() for c in f)]
    if not filas:
        raise ArchivoInvalido("El archivo está vacío.")
    if len(filas) < 2:
        raise ArchivoInvalido("El archivo solo tiene la fila de títulos, sin reservas. "
                              "Revisá las fechas elegidas al exportar en Airbnb.")
    return filas


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
    no_detectadas = [c for c in REQUERIDAS if c not in mapa]
    return mapa, no_detectadas


def parsear_monto(texto):
    if texto is None:
        return 0.0
    t = str(texto).strip().replace("−", "-")   # signo menos unicode
    if not t:
        return 0.0
    negativo = t.startswith("(") and t.endswith(")")  # (45.00) = negativo
    # ### CAMBIO AQUÍ ### notación científica de Excel (4,5E+04)
    m = re.fullmatch(r"-?\d+([.,]\d+)?[eE][+-]?\d+", t)
    if m:
        try:
            return float(t.replace(",", "."))
        except ValueError:
            pass
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
    elif re.fullmatch(r"-?[1-9]\d{0,2}([.,]\d{3})+", limpio):
        limpio = limpio.replace(".","").replace(",","")        # 45.000 / 45,000 (no "0,500")
    elif "," in limpio:
        limpio = limpio.replace(",",".")                       # 45,5
    try:
        return float(limpio)
    except ValueError:
        return 0.0


def _entero(texto):
    """### CAMBIO AQUÍ ### "3", "3.0", "3,0" → 3 (antes "3.0" daba 0 noches)."""
    try:
        return int(round(float(str(texto).strip().replace(",", "."))))
    except (TypeError, ValueError):
        return 0


def parsear_fecha(texto, orden="dmy"):
    """### CAMBIO AQUÍ ### orden: 'dmy' (día/mes, Airbnb en español) o 'mdy' (mes/día, Airbnb en inglés).
    Antes "10/05/2026" del export en inglés (5 de octubre) se leía como 10 de mayo.
    También acepta fechas con hora ("2026-10-05 00:00:00") y con nombre de mes ("Oct 5, 2026", "5 oct. 2026")."""
    if not texto:
        return None
    t = str(texto).strip()
    t = re.split(r"[T ]\d{1,2}:\d{2}", t)[0].strip()   # saca la hora
    barra = ["%d/%m/%Y", "%m/%d/%Y"] if orden == "dmy" else ["%m/%d/%Y", "%d/%m/%Y"]
    formatos = ["%Y-%m-%d"] + barra + ["%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y",
                "%m/%d/%y" if orden == "mdy" else "%d/%m/%y"]
    for fmt in formatos:
        try:
            d = datetime.strptime(t, fmt)
            if 2000 <= d.year <= 2100:
                return d.strftime("%Y-%m-%d")
        except ValueError:
            continue
    # con nombre de mes, en inglés o castellano
    limpio = _norm(t).replace(".", " ").replace(",", " ").replace(" de ", " ")
    partes = limpio.split()
    if len(partes) == 3:
        try:
            if partes[0] in MESES:        # Oct 5 2026
                mes, dia, anio = MESES[partes[0]], int(partes[1]), int(partes[2])
            elif partes[1] in MESES:      # 5 oct 2026
                dia, mes, anio = int(partes[0]), MESES[partes[1]], int(partes[2])
            else:
                return None
            if anio < 100:
                anio += 2000
            return date(anio, mes, dia).isoformat()
        except (ValueError, KeyError):
            return None
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
                                 "tarifa de servicio", "amount", "importe", "type", "tipo", "host fee")}
    return "ganancias" if enc & claves else "reservas"


def _moneda(texto):
    """'USD'/'ARS', '' si no vino, o el código tal cual si es otra moneda (EUR, BRL…)."""
    t = (texto or "").strip().upper()
    if t in ("USD", "US$", "U$S", "DOLARES", "DÓLARES"):
        return "USD"
    if t in ("ARS", "$", "PESOS", "AR$"):
        return "ARS"
    return t


# ### CAMBIO AQUÍ ### tipos de movimiento del Historial de transacciones
def _clase_movimiento(tipo):
    if not tipo:
        return "reserva"
    if tipo in ("payout", "pago", "transferencia") or "transfer" in tipo:
        return "pago"                       # transferencia al banco: no es una reserva
    if "coanfitri" in tipo or "co-host" in tipo or "cohost" in tipo:
        return "coanfitrion"
    if any(p in tipo for p in ("ajust", "adjust", "resolu", "cancellation fee", "tarifa de cancel",
                               "penalidad", "penalty", "reembolso", "refund")):
        return "ajuste"                     # se suma a la reserva con el mismo código
    if "reserv" in tipo or tipo in ("completada", "completed", "booking"):
        return "reserva"
    return "otro"


# ### CAMBIO AQUÍ ### estados que NO son una reserva real (consultas, vencidas, rechazadas)
NO_RESERVA = ("expir", "vencid", "declin", "rechaz", "withdraw", "retir", "inquiry", "consulta",
              "pre-approv", "preaprob", "pre-aprob", "not possible", "no es posible")


def _estado(estado_txt):
    if not estado_txt:
        return "completada"
    if any(p in estado_txt for p in NO_RESERVA):
        return None
    if "cancel" in estado_txt:
        return "cancelada"
    if any(p in estado_txt for p in ("pendiente", "pending", "solicit", "request", "esperando")):
        return "pendiente"
    if any(p in estado_txt for p in ("past", "anterior", "complet", "finaliz", "review", "resena", "reseña")):
        return "completada"   # "Past guest" / "Huésped anterior" / "Review guest"
    return "confirmada"


def procesar_csv(contenido_bytes, mapa_columnas, propiedad_map):
    """
    contenido_bytes : bytes del CSV subido
    mapa_columnas   : { clave_interna: indice_columna }
    propiedad_map   : { nombre_anuncio_csv: propiedad_id }
    Devuelve (filas_ok, omitidas, movimientos). Cada omitida: {fila, motivo, clase: 'error'|'ignorada'}.
    ### CAMBIO AQUÍ ### movimientos: cada cobro/ajuste del Historial de transacciones por separado.
    Se guardan en la base sin repetir, y el monto de cada reserva es la SUMA de sus movimientos:
    así importar meses que se superponen, o una estadía larga cobrada en varios meses, da siempre bien.
    """
    texto = decodificar(contenido_bytes) if isinstance(contenido_bytes, (bytes, bytearray)) else contenido_bytes
    todas = leer_filas(texto)
    encabezados = todas[0]
    # ### CAMBIO AQUÍ ### formato de fecha del archivo (día/mes o mes/día)
    orden = detectar_orden_fechas(todas[1:], [mapa_columnas.get(k) for k in ("fecha_inicio", "fecha_fin", "fecha_reserva")],
                                  _es_ingles(encabezados))
    es_ganancias = tipo_de_archivo(encabezados) == "ganancias"
    # Export viejo sin "Gross earnings": bruto = lo cobrado + la comisión
    bruto_es_neto = (mapa_columnas.get("ingreso_bruto") is not None
                     and mapa_columnas.get("ingreso_bruto") == mapa_columnas.get("ingreso_neto"))

    filas_ok, omitidas = [], []
    por_codigo = {}   # ### CAMBIO AQUÍ ### estadías largas: Airbnb parte el pago en varias filas con el mismo código
    ajustes = []
    movimientos = []

    def error(num, motivo):
        omitidas.append({"fila": num, "motivo": motivo, "clase": "error"})

    def ignorada(num, motivo):
        omitidas.append({"fila": num, "motivo": motivo, "clase": "ignorada"})

    for num, fila in enumerate(todas[1:], start=2):
        def col(clave, default=""):
            idx = mapa_columnas.get(clave)
            if idx is None or idx >= len(fila):
                return default
            return (fila[idx] or "").strip()

        tipo_txt = col("tipo", "")
        clase = _clase_movimiento(_norm(tipo_txt))
        if clase == "pago":
            continue   # transferencia al banco: no es una reserva (no cuenta como error)
        if clase == "coanfitrion":
            ignorada(num, f"Pago al coanfitrión ({tipo_txt}): no es una reserva")
            continue
        if clase == "otro":
            ignorada(num, f"Movimiento '{tipo_txt}': no es una reserva")
            continue

        codigo = col("codigo_confirmacion")
        if clase == "ajuste":
            monto = parsear_monto(col("ingreso_neto")) or parsear_monto(col("ingreso_bruto"))
            ajustes.append((num, codigo, tipo_txt, monto))
            if codigo and monto and es_ganancias:
                movimientos.append({"codigo": codigo[:60], "fecha": parsear_fecha(col("fecha_movimiento"), orden) or "",
                                    "tipo": "ajuste", "bruto": monto, "neto": monto, "comision": 0, "limpieza": 0})
            continue
        if not codigo:
            error(num, "Sin código de confirmación")
            continue

        estado = _estado(_norm(col("estado", "")))
        if estado is None:
            ignorada(num, f"{codigo}: '{col('estado')}' no es una reserva confirmada")
            continue

        anuncio = col("anuncio")
        propiedad_id = propiedad_map.get(anuncio)
        if not propiedad_id:
            ignorada(num, f"Anuncio '{anuncio}' sin asignar a una propiedad")
            continue

        fecha_inicio = parsear_fecha(col("fecha_inicio"), orden)
        fecha_fin    = parsear_fecha(col("fecha_fin"), orden)
        if not fecha_inicio:   # ### CAMBIO AQUÍ ### sin fecha la reserva no sirve para ninguna métrica
            error(num, f"{codigo}: fecha de llegada inválida ('{col('fecha_inicio')}')")
            continue
        if fecha_fin and fecha_fin <= fecha_inicio:
            error(num, f"{codigo}: la salida ({col('fecha_fin')}) es anterior o igual a la llegada")
            continue

        moneda = _moneda(col("moneda"))
        if moneda not in ("", "ARS", "USD"):
            error(num, f"{codigo}: moneda '{moneda}' no soportada (el sistema maneja pesos y dólares)")
            continue

        noches = _entero(col("noches", "0"))
        ingreso_bruto   = parsear_monto(col("ingreso_bruto"))
        comision_airbnb = parsear_monto(col("comision_airbnb"))
        limpieza        = parsear_monto(col("limpieza"))
        ingreso_neto    = parsear_monto(col("ingreso_neto"))
        if bruto_es_neto and es_ganancias and comision_airbnb:
            ingreso_bruto = ingreso_neto + abs(comision_airbnb)
        if ingreso_neto == 0 and ingreso_bruto > 0:
            ingreso_neto = ingreso_bruto - abs(comision_airbnb)  # ### CAMBIO AQUÍ ### la comisión viene negativa
        if estado == "cancelada" and not es_ganancias:
            # ### CAMBIO AQUÍ ### en el archivo de Reservas el monto de una cancelada puede ser el original:
            # no se cuenta. Si Airbnb pagó algo por la cancelación, llega con el archivo de Ganancias.
            ingreso_bruto = ingreso_neto = comision_airbnb = limpieza = 0.0

        fecha_res = parsear_fecha(col("fecha_reserva"), orden)
        anticipacion = None
        if fecha_res and fecha_inicio:
            anticipacion = (datetime.strptime(fecha_inicio, "%Y-%m-%d") -
                            datetime.strptime(fecha_res, "%Y-%m-%d")).days
            if anticipacion < 0:
                anticipacion = None

        nueva = {
            "propiedad_id":        propiedad_id,
            "codigo_confirmacion": codigo[:60],
            "fecha_inicio":        fecha_inicio,
            "fecha_fin":           fecha_fin,
            "noches":              noches,
            "ingreso_bruto":       ingreso_bruto,
            "comision_airbnb":     comision_airbnb,
            "limpieza":            limpieza,
            "ingreso_neto":        ingreso_neto,
            "anticipacion_dias":   anticipacion,
            "fecha_reserva":       fecha_res,   # ### CAMBIO AQUÍ ### cuándo se hizo la reserva (historial)
            "huesped_nombre":      col("huesped_nombre")[:120],
            "moneda":              moneda,   # ### CAMBIO AQUÍ ### vacío = moneda de la propiedad
            "estado":              estado,
            "_inicios":            {fecha_inicio},
        }
        if es_ganancias:
            movimientos.append({"codigo": codigo[:60], "fecha": parsear_fecha(col("fecha_movimiento"), orden) or "",
                                "tipo": "reserva", "bruto": ingreso_bruto, "neto": ingreso_neto,
                                "comision": comision_airbnb, "limpieza": limpieza})
        # ### CAMBIO AQUÍ ### mismo código en varias filas → se suman los montos (no se pisa)
        prev = por_codigo.get(codigo)
        if prev:
            for k in ("ingreso_bruto", "comision_airbnb", "limpieza", "ingreso_neto"):
                prev[k] = round(prev[k] + nueva[k], 2)
            if fecha_inicio in prev["_inicios"]:
                prev["noches"] = max(prev["noches"], noches)
            else:
                prev["noches"] += noches   # tramos mensuales de una estadía larga
                prev["_inicios"].add(fecha_inicio)
            prev["fecha_inicio"] = min(prev["fecha_inicio"], fecha_inicio)
            fines = [x for x in (prev["fecha_fin"], fecha_fin) if x]
            prev["fecha_fin"] = max(fines) if fines else None
            continue
        por_codigo[codigo] = nueva
        filas_ok.append(nueva)

    # ### CAMBIO AQUÍ ### ajustes y resoluciones: se suman a su reserva (antes se perdían como "error")
    for num, codigo, tipo_txt, monto in ajustes:
        r = por_codigo.get(codigo)
        if r and monto:
            r["ingreso_neto"] = round(r["ingreso_neto"] + monto, 2)
            r["ingreso_bruto"] = round(r["ingreso_bruto"] + monto, 2)
        elif monto and not codigo:
            ignorada(num, f"Ajuste '{tipo_txt}' de {monto:,.2f} sin código de reserva"
                     .replace(",", "X").replace(".", ",").replace("X", "."))

    for f in filas_ok:
        f.pop("_inicios", None)
        if f["fecha_inicio"] and f["fecha_fin"]:   # noches: siempre coherentes con las fechas
            calc = (datetime.strptime(f["fecha_fin"], "%Y-%m-%d") -
                    datetime.strptime(f["fecha_inicio"], "%Y-%m-%d")).days
            if calc > 0:
                f["noches"] = calc
        elif f["noches"] and f["fecha_inicio"]:
            f["fecha_fin"] = (datetime.strptime(f["fecha_inicio"], "%Y-%m-%d").date()
                              + timedelta(days=f["noches"])).isoformat()
    return filas_ok, omitidas, movimientos
