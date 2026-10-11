# ayuda.py
# ### CAMBIO AQUÍ ### — Archivo nuevo: textos del ícono "i" (pasar el mouse o tocar en el celular).
# En las plantillas se usa así:  {{ info('adr') }}
# Para cambiar un texto, editalo acá: se actualiza en todas las pantallas.

from markupsafe import Markup, escape

AYUDA = {
    # ── Generales ──────────────────────────────────────────────
    "ver_en": "Elegí en qué moneda ver los totales. Cada propiedad guarda sus montos en su propia moneda; acá solo se convierten para mostrarlos.",
    "tipo_cambio": "Pesos por dólar que usa el sistema para convertir. Podés traerlo de dolarapi.com (MEP, blue, oficial…) o cargarlo a mano.",
    # ── Dashboard ──────────────────────────────────────────────
    "dashboard": "Resumen del negocio en el período elegido. Usá el filtro para ver una propiedad o todas, y las fechas.",
    "filtro": "Filtra los números del dashboard por propiedad y por fechas. Cuentan las noches que caen dentro de esas fechas (una estadía que cruza de mes se reparte entre los dos).",
    "reservas": "Cantidad de reservas con al menos una noche dentro del período elegido (sin contar las canceladas).",
    "ocupacion": "Porcentaje de noches vendidas sobre las noches disponibles (días del período × propiedades activas). Las canceladas no cuentan.",
    "adr": "ADR: precio promedio cobrado por cada noche vendida, sin la tarifa de limpieza. Ingreso de alojamiento ÷ noches ocupadas.",
    "revpar": "RevPAR: ingreso por noche disponible, vendida o no. Combina precio y ocupación: es la mejor medida de rendimiento.",
    "ingreso_bruto": "Lo que pagaron los huéspedes, antes de descontar comisiones y costos.",
    "ingreso_neto_real": "Lo que te queda: lo que te paga Airbnb (ya sin su comisión) menos los costos fijos del período (expensas, servicios, limpieza…).",
    "estadia": "Cantidad promedio de noches por reserva.",
    "anticipacion": "Con cuántos días de anticipación reservan en promedio. Sirve para saber cuándo ajustar precios.",
    "resenas_pend": "Reseñas cargadas que todavía no respondiste. Tocá para ir a responderlas.",
    "ocup_7": "Porcentaje de tus propiedades ocupadas cada noche de la última semana.",
    "proximas": "Reservas que todavía no empezaron. Aparecen si importás el CSV de Reservas de Airbnb.",
    "ingresos_mes": "Ingreso bruto de cada mes (últimos 12 meses como mínimo), en la moneda elegida arriba. Cada reserva aporta a cada mes según sus noches.",
    "noches_mes": "Noches vendidas por mes, sumando las propiedades filtradas.",
    "generar_informe": "La IA escribe un informe con los números del período: resumen, análisis, riesgos y recomendaciones. Queda guardado en Informes.",
    # ── Propiedades ────────────────────────────────────────────
    "alertas": "El sistema revisa solo tus datos y avisa: reservas que se pisan, solicitudes sin confirmar, cobros que faltan, archivos viejos, datos incompletos, noches libres y precios lejos del mercado. Rojo = revisar ya; naranja = pendiente; azul = oportunidad. Cuando lo solucionás, la alerta desaparece sola. Si no te interesa, tocá la ✕ y se oculta 7 días (si el problema sigue, vuelve a aparecer).",
    "calendario": "Cada día muestra cuánto está ocupado y si alguien llega, se va, hubo un cobro o una novedad. Tocá un día para ver el detalle.",
    "nombre_prop": "Cómo la llamás vos para reconocerla (no tiene que ser igual al título de Airbnb). Ej: Depto Soho 2 amb.",
    "ubicacion": "Elegí país, provincia y ciudad de la lista (o escribila si no aparece). Ciudad y barrio se usan para buscar la competencia de la zona.",
    "propiedades": "Tus unidades. Cada una tiene su moneda, sus costos y la información que usa el asistente para responder a huéspedes.",
    "huespedes_prop": "Reservas importadas de la propiedad elegida, con huésped, fechas, plataforma, monto y estado.",
    "estado_prop": "Activa: se alquila. Mantenimiento: temporalmente fuera. Inactiva: no cuenta en ocupación ni en la búsqueda automática.",
    "moneda_prop": "Moneda en la que cobrás esta propiedad. El precio base y los costos se cargan en esta moneda.",
    "puntaje": "Tu puntaje en Airbnb (ej: 4,85). Se usa para el precio sugerido: si es mejor que el de la competencia, podés cobrar más.",
    "cant_resenas": "Cantidad de reseñas en Airbnb. Más reseñas dan más confianza y sostienen un precio más alto.",
    "precio_base": "Lo que cobrás normalmente por noche. Se compara contra el mercado.",
    "costos_fijos": "Gastos mensuales fijos de la propiedad. Se descuentan del ingreso y marcan el precio mínimo para no perder plata.",
    "info_huespedes": "WiFi, horarios, reglas, cómo llegar… El asistente responde a los huéspedes SOLO con lo que escribas acá.",
    # ── Importar ───────────────────────────────────────────────
    "importar": "Subí los CSV que exporta Airbnb. El de Reservas trae las futuras con huésped y estado; el de Ganancias trae los montos exactos. Se combinan sin duplicar, aunque subas el mismo período dos veces.",
    "asignar_anuncios": "Indicá a qué propiedad del sistema corresponde cada anuncio del archivo. Los que no asignes no se importan.",
    # ── Precios ────────────────────────────────────────────────
    "precios": "Calcula un precio por noche para una fecha, partiendo de la competencia y ajustando por tu puntaje, reseñas, temporada, ocupación y fin de semana.",
    "mercado": "Precios de la competencia encontrados en la sección Competencia, pasados a la moneda de la propiedad.",
    "precio_min": "Lo mínimo recomendado. Nunca baja de tus costos fijos por noche + 15%.",
    "precio_sug": "El precio que conviene cobrar esa fecha según el mercado y tus números.",
    "precio_max": "Techo recomendado: más arriba es probable que pierdas reservas.",
    "como_calculo": "Cada paso multiplica el precio anterior. Más de ×1,00 sube el precio; menos de ×1,00 lo baja.",
    # ── Asistente ──────────────────────────────────────────────
    "asistente_negocio": "Preguntale lo que quieras sobre tus propiedades, ingresos, precios o competencia. Usa los datos reales del sistema.",
    "consultas": "Pegá el mensaje de un huésped y la IA arma la respuesta con la información de la propiedad. Si no sabe algo, queda Pendiente para que respondas vos.",
    "resenas": "Pegá una reseña de Airbnb y la IA prepara una respuesta pública. Revisala, copiala y marcala como respondida.",
    # ── Informes ───────────────────────────────────────────────
    "informes": "Informes generados por la IA. Podés verlos, imprimirlos o descargarlos en PDF y Excel.",
    # ── Competencia ────────────────────────────────────────────
    "competencia": "Precios por noche de alojamientos parecidos a los tuyos (misma ciudad, barrio y cantidad de ambientes), buscados en internet.",
    "auto_competencia": "Todas las noches el sistema actualiza solo la competencia. Las propiedades del mismo barrio y con los mismos ambientes comparten la búsqueda, y los precios se acumulan 30 días. Las búsquedas del mes se reparten para que no se terminen antes de fin de mes.",
    "buscar_comparables": "Busca ahora en Google los alquileres vacacionales del barrio (Airbnb, VRBO, Booking…) con precio por noche. Gasta 1 o 2 de las 250 búsquedas gratis del mes.",
    "mediana": "El precio del medio: la mitad de la competencia cobra menos y la otra mitad más. Es más confiable que el promedio.",
    "tendencia": "Cómo cambió la mediana del mercado en las últimas búsquedas. Sirve para ver si la zona sube o baja.",
    "zona_aprox": "Las plataformas no muestran la dirección exacta hasta que se reserva; por eso la zona es aproximada.",
    # ### CAMBIO AQUÍ ### modo mixto de competencia
    "referencia_zona": "Mediana de los precios por noche de la zona: los que encontró la IA en los últimos 30 días más los competidores que cargaste vos. Cuantos más datos, más confiable.",
    "fuentes_busqueda": "Primero Google (alquileres vacacionales, precio real por noche). Si falla o se terminan las búsquedas del mes, Tavily. Así la competencia no se queda sin datos.",
    "alerta_competencia": "Aparece si durante 3 días seguidos ninguna fuente trajo precios de la competencia. Debajo figura el motivo.",
    "archivo_anual": "Al terminar cada año, descargá su archivo: resumen en Excel, reservas, reseñas e informes del año, copia completa de la base y del código, y cómo restaurar el sistema. Los datos no se borran del sistema.",
    "respaldo": "Descarga todas las tablas (propiedades, reservas, reseñas, competencia...) en archivos CSV. Además el sistema hace una copia automática cifrada todas las semanas. Hacelo una vez por mes como copia extra.",
    "competidor_directo": "Opcional: un anuncio parecido al tuyo que conocés. Cargá su precio por noche. Nunca se borra solo.",
}


def info(clave, texto=None):
    """Devuelve el ícono 'i' con su explicación (mouse encima o toque en el celular)."""
    t = texto or AYUDA.get(clave, "")
    if not t:
        return ""
    return Markup(f'<button type="button" class="info" aria-label="Más información" data-tip="{escape(t)}">i</button>')
