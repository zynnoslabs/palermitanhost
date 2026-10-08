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


def armar_alias(filas):
    """filas: [(nombre, id_minimo_de_reserva)] → {nombre: 'Huésped #id'}"""
    alias = {}
    for nombre, rid in filas:
        n = (nombre or "").strip()
        if n and n not in alias:
            alias[n] = f"Huésped #{rid}"
    return alias


def _patrones(alias):
    """Lista (texto_normalizado, alias) ordenada de más largo a más corto.
    Incluye el nombre completo y cada palabra suelta (si es de UN solo huésped)."""
    pats = {}
    por_palabra = {}
    for nombre, a in alias.items():
        pats[_norm(nombre)] = a
        for palabra in re.findall(r"\w+", _norm(nombre)):
            if len(palabra) >= MIN_LARGO_PALABRA:
                por_palabra.setdefault(palabra, set()).add(a)
    for palabra, dueños in por_palabra.items():
        if len(dueños) == 1 and palabra not in pats:
            pats[palabra] = next(iter(dueños))
    return sorted(pats.items(), key=lambda x: -len(x[0]))


def ocultar(texto, alias):
    """Reemplaza los nombres de huéspedes por su alias. Devuelve (texto, aliases_usados)."""
    if not texto or not alias:
        return texto, set()
    norm = _norm(texto)
    ocupado = [False] * len(texto)
    cambios = []   # (inicio, fin, alias)
    for patron, a in _patrones(alias):
        for m in re.finditer(r"(?<!\w)" + re.escape(patron) + r"(?!\w)", norm):
            i, j = m.span()
            if any(ocupado[i:j]):
                continue
            for k in range(i, j):
                ocupado[k] = True
            cambios.append((i, j, a))
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
