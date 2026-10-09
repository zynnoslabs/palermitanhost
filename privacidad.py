# privacidad.py
# ### CAMBIO AQUÍ ### — Archivo nuevo: los nombres de los huéspedes NUNCA viajan a la IA (Groq).
#
# Antes de mandar un mensaje a Groq, cada nombre de huésped se reemplaza por un alias
# ("Huésped #12"). Cuando vuelve la respuesta, el alias se cambia otra vez por el nombre real.
# Así Adriano ve los nombres en pantalla, pero la IA (que está en Estados Unidos) no los recibe.
# Esto cumple con el principio de "minimizar datos" de la Ley 25.326.

import re
import unicodedata

MIN_LARGO_PALABRA = 4   # "Juan" sí; "Sol", "Ana" no (demasiado comunes en el texto)
RE_ALIAS = re.compile(r"hu[eé]sped\s*#\s*(\d+)", re.IGNORECASE)


def _norm_char(c):
    """Minúscula y sin acento, SIEMPRE 1 carácter (para no correr las posiciones)."""
    d = unicodedata.normalize("NFD", c.lower())
    base = "".join(x for x in d if unicodedata.category(x) != "Mn")
    return base[:1] if base else c


def _norm(texto):
    return "".join(_norm_char(c) for c in texto)


# ### CAMBIO AQUÍ ### palabras que NUNCA se tapan solas aunque un huésped se llame así
# (antes "¿cuánto pagué de luz?" se mandaba como "¿cuánto pagué de Huésped #3?").
NO_TAPAR = set("""
enero febrero marzo abril mayo junio julio agosto septiembre setiembre octubre noviembre diciembre
lunes martes miercoles jueves viernes sabado domingo
luz sol mar paz rosa flor cielo estrella perla rocio aurora alba gloria victoria pilar consuelo amparo
dolores angeles reyes cruz mercedes esperanza fe nieves soledad milagros remedios asuncion
santos leon blanco rubio moreno castillo bravo rios campos delgado franco fuentes salvador vega
nuevo nueva grande chico chica santa santo norte sur este oeste centro
palermo recoleta belgrano nunez caballito almagro villa crespo urquiza devoto soho hollywood retiro
boedo colegiales telmo boca puerto madero balvanera congreso tribunales once flores floresta
saavedra coghlan chacarita barracas pompeya mataderos liniers versalles parque patricios agronomia
buenos aires argentina cordoba mendoza rosario salta tucuman bariloche ushuaia jujuy neuquen
madrid paris london londres roma miami chile uruguay brasil mexico peru espana
airbnb booking google whatsapp
""".split())


def armar_alias(filas):
    """filas: [(nombre, id_minimo_de_reserva)] → {nombre: 'Huésped #id'}
    ### CAMBIO AQUÍ ### el mismo nombre escrito con o sin acento/mayúsculas es la MISMA persona."""
    alias, por_norm = {}, {}
    for nombre, rid in filas:
        n = re.sub(r"\s+", " ", (nombre or "").strip())
        if not n or n in alias:
            continue
        k = _norm(n)
        if k not in por_norm:
            por_norm[k] = f"Huésped #{rid}"
        alias[n] = por_norm[k]
    return alias


def _patrones(alias):
    """Lista (texto_normalizado, alias) ordenada de más largo a más corto.
    Incluye el nombre completo y cada palabra suelta (si es de UN solo huésped)."""
    pats = {}
    por_palabra = {}
    for nombre, a in alias.items():
        completo = _norm(nombre)
        if " " in completo or completo not in NO_TAPAR:
            pats[completo] = a
        for palabra in re.findall(r"\w+", completo):
            if len(palabra) >= MIN_LARGO_PALABRA and palabra not in NO_TAPAR:
                por_palabra.setdefault(palabra, set()).add(a)
    for palabra, dueños in por_palabra.items():
        if len(dueños) == 1 and palabra not in pats:
            pats[palabra] = next(iter(dueños))
    return sorted(pats.items(), key=lambda x: -len(x[0]))


_cache = {"clave": None, "regex": None, "mapa": None}


def _regex(alias):
    """### CAMBIO AQUÍ ### una sola búsqueda para todos los nombres (antes una por nombre: con cientos
    de huéspedes cada mensaje tardaba segundos)."""
    clave = tuple(sorted(alias.items()))
    if _cache["clave"] != clave:
        pats = _patrones(alias)
        _cache["mapa"] = dict(pats)
        _cache["regex"] = (re.compile(r"(?<!\w)(?:" + "|".join(re.escape(p) for p, _ in pats) + r")(?!\w)")
                           if pats else None)
        _cache["clave"] = clave
    return _cache["regex"], _cache["mapa"]


def ocultar(texto, alias):
    """Reemplaza los nombres de huéspedes por su alias. Devuelve (texto, aliases_usados)."""
    if not texto or not alias:
        return texto, set()
    regex, mapa = _regex(alias)
    if regex is None:
        return texto, set()
    norm = _norm(texto)   # misma longitud que el texto: las posiciones coinciden
    cambios = [(m.start(), m.end(), mapa[m.group(0)]) for m in regex.finditer(norm)]
    usados = set()
    for i, j, a in sorted(cambios, reverse=True):
        texto = texto[:i] + a + texto[j:]
        usados.add(a)
    return texto, usados


def mostrar(texto, alias):
    """Cambia 'Huésped #12' por el nombre real (para mostrarle la respuesta a Adriano)."""
    if not texto or not alias:
        return texto
    por_id = {a.split("#")[1]: nombre for nombre, a in alias.items()}
    return RE_ALIAS.sub(lambda m: por_id.get(m.group(1), m.group(0)), texto)
