"""
errores.py — Catálogo de códigos de error de PalermitanHost
Cada error tiene un código único, descripción técnica y qué hacer.
Cuando el sistema muestra un código, pasáselo al desarrollador.
"""

CODIGOS = {

    # ══ SCRAPER (SCR) ════════════════════════════════════════════════════════
    "ERR-SCR-001": {
        "area": "Scraper de precios",
        "archivo": "scraper.py → scrape_precios_zona()",
        "descripcion": "Timeout: Airbnb no respondió en 15 segundos.",
        "causa_probable": "Airbnb lento o sin conexión a internet en el servidor.",
        "accion": "Reintentar en unos minutos. Si persiste, verificar conectividad del servidor.",
    },
    "ERR-SCR-002": {
        "area": "Scraper de precios",
        "archivo": "scraper.py → scrape_precios_zona()",
        "descripcion": "Error de conexión al contactar Airbnb.",
        "causa_probable": "Sin internet, DNS caído o Airbnb bloqueó la IP del servidor.",
        "accion": "Verificar que el servidor Render tiene salida a internet. Puede requerir cambiar User-Agent.",
    },
    "ERR-SCR-003": {
        "area": "Scraper de precios",
        "archivo": "scraper.py → scrape_precios_zona()",
        "descripcion": "Airbnb devolvió HTTP 403 (acceso denegado) o 429 (demasiadas solicitudes).",
        "causa_probable": "Airbnb detectó el scraping y bloqueó temporalmente.",
        "accion": "Esperar 1-2 horas. Si persiste, actualizar el User-Agent en scraper.py o agregar delays.",
    },
    "ERR-SCR-004": {
        "area": "Scraper de precios",
        "archivo": "scraper.py → _extraer_datos()",
        "descripcion": "Scraping completado pero sin precios extraíbles.",
        "causa_probable": "Airbnb cambió la estructura HTML de su página de búsqueda.",
        "accion": "Revisar el HTML actual de Airbnb y actualizar los selectores en _extraer_datos().",
    },
    "ERR-SCR-005": {
        "area": "Scraper de precios",
        "archivo": "scraper.py → scrape_precios_zona()",
        "descripcion": "Error inesperado durante el scraping (no clasificado).",
        "causa_probable": "Error de código o respuesta inesperada de Airbnb.",
        "accion": "Ver el mensaje completo en los logs de Render para diagnóstico.",
    },

    # ══ BASE DE DATOS (DB) ════════════════════════════════════════════════════
    "ERR-DB-001": {
        "area": "Base de datos",
        "archivo": "database.py → get_db_connection()",
        "descripcion": "No se pudo conectar a PostgreSQL.",
        "causa_probable": "Variable DATABASE_URL mal configurada o base de datos de Render caída.",
        "accion": "Verificar DATABASE_URL en las variables de entorno de Render.",
    },
    "ERR-DB-002": {
        "area": "Base de datos",
        "archivo": "database.py → init_db()",
        "descripcion": "Error al crear las tablas iniciales.",
        "causa_probable": "Permisos insuficientes en la DB o sintaxis SQL incompatible.",
        "accion": "Revisar logs de inicio en Render. Ejecutar init_db() manualmente si es necesario.",
    },
    "ERR-DB-003": {
        "area": "Base de datos",
        "archivo": "Cualquier ruta → consulta SQL",
        "descripcion": "Error en una consulta SQL durante operación normal.",
        "causa_probable": "Tabla no existe, columna faltante o tipo de dato incorrecto.",
        "accion": "Ver el log completo en Render. Probablemente falta ejecutar una migración.",
    },

    # ══ IMPORTACIÓN CSV (IMP) ═════════════════════════════════════════════════
    "ERR-IMP-001": {
        "area": "Importación CSV",
        "archivo": "importador.py → procesar_csv()",
        "descripcion": "El archivo subido no es un CSV válido de Airbnb.",
        "causa_probable": "CSV corrupto, formato incorrecto o exportado desde sección equivocada.",
        "accion": "Ir a Airbnb → Ganancias → Exportar CSV. Asegurarse de no modificar el archivo antes de subir.",
    },
    "ERR-IMP-002": {
        "area": "Importación CSV",
        "archivo": "importador.py → procesar_csv()",
        "descripcion": "El CSV no tiene las columnas esperadas.",
        "causa_probable": "Airbnb cambió el formato de exportación.",
        "accion": "Abrir el CSV con Excel, ver los nombres de columnas y actualizar el mapeo en importador.py.",
    },
    "ERR-IMP-003": {
        "area": "Importación CSV",
        "archivo": "importador.py → procesar_csv()",
        "descripcion": "Error al insertar filas en la base de datos durante la importación.",
        "causa_probable": "Datos duplicados o tipo de dato inesperado en alguna columna.",
        "accion": "Ver qué fila específica causó el error en los logs. Puede requerir limpiar la tabla reservas.",
    },

    # ══ ASISTENTE IA (IA) ═════════════════════════════════════════════════════
    "ERR-IA-001": {
        "area": "Asistente IA",
        "archivo": "asistente_route.py → chat()",
        "descripcion": "Error al conectar con Groq (API de IA).",
        "causa_probable": "GROQ_API_KEY inválida, expirada o no configurada en Render.",
        "accion": "Verificar GROQ_API_KEY en las variables de entorno de Render. Generar nueva key en console.groq.com.",
    },
    "ERR-IA-002": {
        "area": "Asistente IA",
        "archivo": "asistente_route.py → chat()",
        "descripcion": "Groq devolvió error de límite de tokens o rate limit.",
        "causa_probable": "Demasiadas consultas seguidas o mensaje muy largo.",
        "accion": "Esperar 1 minuto y reintentar. Si persiste, reducir MAX_HISTORIAL en asistente_route.py.",
    },
    "ERR-IA-003": {
        "area": "Asistente IA",
        "archivo": "asistente_route.py → build_context()",
        "descripcion": "Error al construir el contexto del negocio para la IA.",
        "causa_probable": "Fallo en consulta SQL al cargar propiedades o reservas.",
        "accion": "Revisar ERR-DB-003. La IA responde igual pero sin datos del negocio.",
    },

    # ══ EXPORTACIÓN (EXP) ════════════════════════════════════════════════════
    "ERR-EXP-001": {
        "area": "Exportación PDF",
        "archivo": "exportar_routes.py → exportar_pdf()",
        "descripcion": "Error al generar el PDF con reportlab.",
        "causa_probable": "reportlab no instalado en Render o contenido del informe con caracteres especiales.",
        "accion": "Verificar que requirements.txt tiene reportlab==4.2.2 y que Render lo instaló.",
    },
    "ERR-EXP-002": {
        "area": "Exportación Excel",
        "archivo": "exportar_routes.py → exportar_excel()",
        "descripcion": "Error al generar el Excel con openpyxl.",
        "causa_probable": "openpyxl no instalado en Render.",
        "accion": "Verificar que requirements.txt tiene openpyxl==3.1.2 y que Render lo instaló.",
    },
    "ERR-EXP-003": {
        "area": "Exportación",
        "archivo": "exportar_routes.py",
        "descripcion": "Informe no encontrado al intentar exportar.",
        "causa_probable": "ID de informe incorrecto o informe eliminado de la base de datos.",
        "accion": "Ir a la lista de informes y verificar que el informe existe.",
    },

    # ══ AUTENTICACIÓN (AUTH) ══════════════════════════════════════════════════
    "ERR-AUTH-001": {
        "area": "Autenticación",
        "archivo": "app.py → login()",
        "descripcion": "Variable APP_PASSWORD no configurada.",
        "causa_probable": "APP_PASSWORD falta en las variables de entorno de Render.",
        "accion": "Agregar APP_PASSWORD en Environment Variables de Render.",
    },

    # ══ PRECIOS (PRC) ════════════════════════════════════════════════════════
    "ERR-PRC-001": {
        "area": "Cálculo de precio estratégico",
        "archivo": "precio_estrategico.py → calcular_precio_estrategico()",
        "descripcion": "Error inesperado en el cálculo de precio.",
        "causa_probable": "Datos de propiedad faltantes (rating None, ambientes None).",
        "accion": "Verificar que la propiedad tiene todos los campos completos en la base de datos.",
    },
    "ERR-PRC-002": {
        "area": "Cálculo de precio estratégico",
        "archivo": "ruta_precios.py → calcular()",
        "descripcion": "Propiedad no encontrada al calcular precio.",
        "causa_probable": "ID de propiedad inválido o propiedad eliminada.",
        "accion": "Recargar la página de precios y seleccionar la propiedad nuevamente.",
    },

}


def get_error(codigo):
    """Devuelve el detalle de un código de error."""
    return CODIGOS.get(codigo, {
        "area": "Desconocido",
        "descripcion": f"Código {codigo} no registrado en el catálogo.",
        "accion": "Pasale el código y el mensaje completo al desarrollador.",
    })


def codigo_para_excepcion(exc, contexto=""):
    """
    Dado un contexto y una excepción, devuelve el código más apropiado.
    Uso: codigo_para_excepcion(e, "scraper-timeout") → "ERR-SCR-001"
    """
    ctx = contexto.lower()
    msg = str(exc).lower()

    if "scraper" in ctx or "scrape" in ctx:
        if "timeout" in msg:              return "ERR-SCR-001"
        if "connection" in msg:           return "ERR-SCR-002"
        if "403" in msg or "429" in msg:  return "ERR-SCR-003"
        if "sin precios" in msg:          return "ERR-SCR-004"
        return "ERR-SCR-005"

    if "db" in ctx or "database" in ctx or "sql" in ctx:
        if "connect" in msg:  return "ERR-DB-001"
        if "init" in ctx:     return "ERR-DB-002"
        return "ERR-DB-003"

    if "importar" in ctx or "csv" in ctx:
        if "columna" in msg or "column" in msg: return "ERR-IMP-002"
        if "insertar" in msg or "insert" in msg: return "ERR-IMP-003"
        return "ERR-IMP-001"

    if "groq" in ctx or "ia" in ctx or "asistente" in ctx:
        if "rate" in msg or "limit" in msg: return "ERR-IA-002"
        if "context" in ctx:                return "ERR-IA-003"
        return "ERR-IA-001"

    if "pdf" in ctx:   return "ERR-EXP-001"
    if "excel" in ctx: return "ERR-EXP-002"
    if "precio" in ctx or "prc" in ctx: return "ERR-PRC-001"

    return "ERR-GEN-000"
