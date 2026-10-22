# database.py
import os
import psycopg2
import psycopg2.extras
import psycopg2.pool
import psycopg2.extensions
import threading
import time
from contextlib import contextmanager

DATABASE_URL = os.getenv("DATABASE_URL")

# ### CAMBIO AQUÍ ### — lazy init: el pool se crea solo cuando se necesita
# ### CAMBIO AQUÍ ### (revisión general):
#  - ThreadedConnectionPool: la búsqueda nocturna corre en un hilo aparte y el pool simple no lo soporta.
#  - Cada conexión se prueba antes de usarla: si la base se reinició, se descarta y se abre otra
#    (antes la primera página después de un reinicio de Render daba error).
#  - Toda conexión trabaja en hora de Buenos Aires.
#  - Al devolverla al pool se cierra cualquier transacción abierta (si no, bloqueaba tablas).
_pool = None
_lock_pool = threading.Lock()
ZONA = "America/Argentina/Buenos_Aires"


def _get_pool():
    global _pool
    if _pool is None:
        with _lock_pool:
            if _pool is None:
                url = os.getenv("DATABASE_URL")
                if not url:
                    raise RuntimeError(
                        "DATABASE_URL no está configurada. "
                        "Añadila en las variables de entorno de Render (o en .env local)."
                    )
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    1, 10, url, connect_timeout=10,
                    keepalives=1, keepalives_idle=60, keepalives_interval=10, keepalives_count=3)
    return _pool


# ### CAMBIO AQUÍ ### — velocidad con base remota (Neon): la conexión se "prueba" con SELECT 1
# solo si estuvo quieta más de 30 s. Antes se probaba en CADA consulta (2 viajes extra a la base).
_ULTIMO_USO = {}
_PROBAR_SI_QUIETA = 30


def get_db():
    pool = _get_pool()
    for intento in range(3):
        conn = pool.getconn()
        try:
            if conn.closed:
                raise psycopg2.InterfaceError("conexión cerrada")
            if (time.monotonic() - _ULTIMO_USO.get(id(conn), 0) < _PROBAR_SI_QUIETA
                    and conn.get_parameter_status("TimeZone") == ZONA):
                return conn
            cur = conn.cursor()
            cur.execute("SELECT 1")
            if conn.get_parameter_status("TimeZone") != ZONA:
                cur.execute("SET TIME ZONE %s", (ZONA,))
            conn.commit()
            cur.close()
            return conn
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            try:
                pool.putconn(conn, close=True)
            except Exception:
                pass
            if intento == 2:
                raise
    return conn


# Alias para compatibilidad con asistente_route.py y exportar_routes.py
def get_db_connection():
    return get_db()


def _release(conn):
    _ULTIMO_USO[id(conn)] = time.monotonic()   # ### CAMBIO AQUÍ ###
    try:
        if not conn.closed and conn.get_transaction_status() != psycopg2.extensions.TRANSACTION_STATUS_IDLE:
            conn.rollback()
        _get_pool().putconn(conn, close=bool(conn.closed))
    except Exception:
        try:
            _get_pool().putconn(conn, close=True)
        except Exception:
            pass

def release_db(conn):
    """Alias público de _release para blueprints externos."""
    _release(conn)


def _rollback(conn):
    try:
        conn.rollback()
    except Exception:
        pass   # si la conexión se cortó, que se vea el error original


@contextmanager
def bloqueo(clave):
    """### CAMBIO AQUÍ ### candado en la base: evita que la búsqueda de competencia corra dos veces a la vez
    (aunque Render tenga 2 procesos). Devuelve True si se obtuvo."""
    conn = get_db()
    obtenido = False
    try:
        cur = conn.cursor()
        cur.execute("SELECT pg_try_advisory_lock(%s)", (clave,))
        obtenido = bool(cur.fetchone()[0])
        conn.commit()
        yield obtenido
    finally:
        try:
            if obtenido:
                cur = conn.cursor()
                cur.execute("SELECT pg_advisory_unlock(%s)", (clave,))
                conn.commit()
        except Exception:
            pass
        _release(conn)


def esta_bloqueado(clave):
    row = query_one("SELECT COUNT(*) AS n FROM pg_locks WHERE locktype='advisory' AND objid=%s AND granted", (clave,))
    return bool(row and row["n"])


def init_db():
    conn = get_db()
    cur = conn.cursor()
    try:
        # ### CAMBIO AQUÍ ### los 2 procesos de Render arrancan a la vez: uno espera al otro
        cur.execute("SET LOCAL lock_timeout = '15s'")
        cur.execute("SELECT pg_advisory_xact_lock(7171)")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS propiedades (
                id               SERIAL PRIMARY KEY,
                nombre           TEXT NOT NULL,
                direccion        TEXT,
                barrio           TEXT,
                tipo             TEXT CHECK(tipo IN ('depto','casa','departamento')),
                ambientes        INTEGER,
                capacidad        INTEGER,
                precio_base      REAL DEFAULT 0,
                costo_expensas   REAL DEFAULT 0,
                costo_servicios  REAL DEFAULT 0,
                costo_limpieza   REAL DEFAULT 0,
                costo_comision   REAL DEFAULT 0,
                info_huespedes   TEXT DEFAULT '',
                descripcion      TEXT DEFAULT '',
                rating           REAL,
                reviews_count    INTEGER DEFAULT 0,
                estado           TEXT DEFAULT 'activa',
                creada_en        TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS reservas (
                id                  SERIAL PRIMARY KEY,
                propiedad_id        INTEGER REFERENCES propiedades(id),
                codigo_confirmacion TEXT UNIQUE,
                huesped_nombre      TEXT DEFAULT '',
                fecha_inicio        TEXT,
                fecha_fin           TEXT,
                noches              INTEGER,
                ingreso_bruto       REAL DEFAULT 0,
                comision_airbnb     REAL DEFAULT 0,
                limpieza            REAL DEFAULT 0,
                ingreso_neto        REAL DEFAULT 0,
                precio_total        REAL GENERATED ALWAYS AS (ingreso_neto) STORED,
                anticipacion_dias   INTEGER,
                canal               TEXT DEFAULT 'airbnb',
                estado              TEXT DEFAULT 'completada',
                notas               TEXT DEFAULT '',
                fuente              TEXT DEFAULT 'csv',
                importado_en        TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS competencia (
                id           SERIAL PRIMARY KEY,
                barrio       TEXT,
                tipo         TEXT,
                ambientes    INTEGER,
                capacidad    INTEGER,
                precio_noche REAL,
                fecha        TEXT,
                fuente       TEXT,
                notas        TEXT,
                cargado_en   TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # ### CAMBIO AQUÍ ### — columnas nuevas para la búsqueda de competencia con IA
        for col_sql in (
            "propiedad_id INTEGER",
            "plataforma   TEXT",
            "titulo       TEXT",
            "zona         TEXT",
            "link         TEXT",
            "rating       REAL",
            "origen       TEXT DEFAULT 'manual'",
        ):
            cur.execute(f"ALTER TABLE competencia ADD COLUMN IF NOT EXISTS {col_sql}")

        # ### CAMBIO AQUÍ ### — moneda (ARS o USD) en propiedades, reservas y competencia
        for tabla in ("propiedades", "reservas", "competencia"):
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS moneda TEXT DEFAULT 'ARS'")
        # ### CAMBIO AQUÍ ### — ciudad de cada propiedad (se usa para buscar la competencia)
        cur.execute("ALTER TABLE propiedades ADD COLUMN IF NOT EXISTS ciudad TEXT DEFAULT 'Buenos Aires'")
        # ### CAMBIO AQUÍ ### montos con precisión completa: REAL guarda solo 7 cifras
        # (208.560,13 quedaba 208.560,12 y montos de millones perdían los últimos pesos)
        cur.execute("""SELECT table_name, column_name FROM information_schema.columns
                       WHERE table_schema = current_schema() AND data_type = 'real'""")
        reales = cur.fetchall()
        if any(t == "reservas" and c == "ingreso_neto" for t, c in reales):
            cur.execute("ALTER TABLE reservas DROP COLUMN IF EXISTS precio_total")
        for t, c in reales:
            if (t, c) != ("reservas", "precio_total"):   # esa se vuelve a crear abajo
                cur.execute(f'ALTER TABLE "{t}" ALTER COLUMN "{c}" TYPE DOUBLE PRECISION')
        if any(t == "reservas" and c == "ingreso_neto" for t, c in reales):
            cur.execute("ALTER TABLE reservas ADD COLUMN precio_total DOUBLE PRECISION GENERATED ALWAYS AS (ingreso_neto) STORED")
        # ### CAMBIO AQUÍ ### historial de cada reserva (novedades, calendario)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reservas_historial (
                id           SERIAL PRIMARY KEY,
                codigo       TEXT NOT NULL,
                propiedad_id INTEGER,
                fecha        TEXT,
                tipo         TEXT,
                detalle      TEXT,
                fecha_real   BOOLEAN DEFAULT FALSE,
                creado_en    TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_historial_codigo ON reservas_historial (codigo)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_historial_fecha ON reservas_historial (fecha)")
        cur.execute("ALTER TABLE reservas ADD COLUMN IF NOT EXISTS fecha_reserva TEXT")
        # ### CAMBIO AQUÍ ### ubicación completa y características de la propiedad
        for col_sql in ("pais TEXT DEFAULT 'Argentina'", "pais_codigo TEXT DEFAULT 'AR'", "provincia TEXT DEFAULT ''",
                        "piso_depto TEXT DEFAULT ''", "m2 INTEGER", "cochera INTEGER DEFAULT 0"):
            cur.execute(f"ALTER TABLE propiedades ADD COLUMN IF NOT EXISTS {col_sql}")
        # ### CAMBIO AQUÍ ### costos por cada salida de huésped (recambio), estadía mínima y calendario iCal
        for col_sql in ("recambio_limpieza DOUBLE PRECISION DEFAULT 0", "recambio_lavanderia DOUBLE PRECISION DEFAULT 0",
                        "recambio_insumos DOUBLE PRECISION DEFAULT 0", "estadia_minima INTEGER", "ical_url TEXT DEFAULT ''"):
            cur.execute(f"ALTER TABLE propiedades ADD COLUMN IF NOT EXISTS {col_sql}")
        # noches ocupadas/bloqueadas según el calendario iCal de Airbnb (se reemplaza en cada lectura)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ical_bloqueos (
                id           SERIAL PRIMARY KEY,
                propiedad_id INTEGER NOT NULL,
                desde        TEXT NOT NULL,
                hasta        TEXT NOT NULL,
                tipo         TEXT DEFAULT 'reservada'
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ical_prop ON ical_bloqueos (propiedad_id)")
        # lo que Adriano marca o comenta sobre cada sugerencia (nunca se borra solo)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS comentarios (
                id        SERIAL PRIMARY KEY,
                clave     TEXT NOT NULL,
                texto     TEXT NOT NULL,
                creado_en TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_comentarios_clave ON comentarios (clave)")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS acciones_estado (
                clave     TEXT PRIMARY KEY,
                estado    TEXT NOT NULL,
                fecha     TEXT NOT NULL
            )
        """)
        # ### CAMBIO AQUÍ ### usuarios extra que crea Adriano (limpieza o co-anfitrión). El dueño sigue entrando con ADMIN_USER/ADMIN_PASS.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id         SERIAL PRIMARY KEY,
                nombre     TEXT NOT NULL,
                usuario    TEXT UNIQUE NOT NULL,
                clave_hash TEXT NOT NULL,
                rol        TEXT NOT NULL CHECK (rol IN ('limpieza', 'coanfitrion')),
                activo     BOOLEAN DEFAULT TRUE,
                creado_en  TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        # ### CAMBIO AQUÍ ### limpiezas marcadas como hechas (clave = propiedad:fecha)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS limpiezas_estado (
                clave     TEXT PRIMARY KEY,
                estado    TEXT NOT NULL,
                quien     TEXT DEFAULT '',
                fecha     TEXT NOT NULL
            )
        """)
        # pruebas de descuento/promoción que Adriano hizo en Airbnb (para medir qué funcionó)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pruebas_descuento (
                id           SERIAL PRIMARY KEY,
                propiedad_id INTEGER NOT NULL,
                fecha        TEXT NOT NULL,
                tipo         TEXT NOT NULL,
                porcentaje   DOUBLE PRECISION DEFAULT 0,
                nota         TEXT DEFAULT '',
                creado_en    TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        # ### CAMBIO AQUÍ ### pruebas con fechas, valor (precio/%/noches) y lo que sugería el sistema en ese momento
        for col_sql in ("desde TEXT", "hasta TEXT", "valor DOUBLE PRECISION", "sugerido DOUBLE PRECISION",
                        "origen TEXT DEFAULT 'manual'", "clave TEXT"):
            cur.execute(f"ALTER TABLE pruebas_descuento ADD COLUMN IF NOT EXISTS {col_sql}")
        # eventos que mueven la demanda (recitales, congresos...). Los feriados se traen solos.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS eventos (
                id        SERIAL PRIMARY KEY,
                desde     TEXT NOT NULL,
                hasta     TEXT NOT NULL,
                nombre    TEXT NOT NULL,
                impacto   INTEGER DEFAULT 10,
                creado_en TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS consultas_huespedes (
                id           SERIAL PRIMARY KEY,
                propiedad_id INTEGER REFERENCES propiedades(id),
                mensaje      TEXT NOT NULL,
                respuesta    TEXT,
                idioma       TEXT,
                pendiente    INTEGER DEFAULT 0,
                creada_en    TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS informes (
                id              SERIAL PRIMARY KEY,
                titulo          TEXT,
                tipo            TEXT DEFAULT 'general',
                fecha_desde     TEXT,
                fecha_hasta     TEXT,
                propiedad_id    INTEGER,
                contenido       TEXT NOT NULL,
                fecha_generado  TIMESTAMPTZ DEFAULT NOW(),
                creado_en       TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # ### CAMBIO AQUÍ ### — historial diario de la competencia (para ver la tendencia)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS competencia_historial (
                id           SERIAL PRIMARY KEY,
                propiedad_id INTEGER REFERENCES propiedades(id) ON DELETE CASCADE,
                fecha        TEXT NOT NULL,
                cantidad     INTEGER,
                mediana      REAL,
                minimo       REAL,
                maximo       REAL,
                moneda       TEXT,
                fuente       TEXT,
                creada_en    TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (propiedad_id, fecha)
            )
        """)

        # ### CAMBIO AQUÍ ### — intentos fallidos de login (para bloquear a quien prueba contraseñas)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS login_intentos (
                ip               TEXT PRIMARY KEY,
                fallos           INTEGER DEFAULT 0,
                ultimo_fallo     TIMESTAMPTZ,
                bloqueado_hasta  TIMESTAMPTZ
            )
        """)

        # ### CAMBIO AQUÍ ### — reseñas de huéspedes (tarjeta "Reseñas pendientes" del dashboard)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS resenas (
                id           SERIAL PRIMARY KEY,
                propiedad_id INTEGER REFERENCES propiedades(id),
                huesped      TEXT DEFAULT '',
                puntaje      INTEGER,
                texto        TEXT NOT NULL,
                respuesta    TEXT DEFAULT '',
                pendiente    INTEGER DEFAULT 1,
                fecha        TEXT,
                creada_en    TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # ### CAMBIO AQUÍ ### cada cobro/ajuste de Airbnb por separado (sin repetir): el monto de cada
        # reserva es la suma de sus cobros, aunque se importen meses que se superponen
        cur.execute("""
            CREATE TABLE IF NOT EXISTS movimientos_airbnb (
                id           SERIAL PRIMARY KEY,
                codigo       TEXT NOT NULL,
                fecha        TEXT DEFAULT '',
                tipo         TEXT DEFAULT 'reserva',
                bruto        NUMERIC(14,2) DEFAULT 0,
                neto         NUMERIC(14,2) DEFAULT 0,
                comision     NUMERIC(14,2) DEFAULT 0,
                limpieza     NUMERIC(14,2) DEFAULT 0,
                importado_en TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (codigo, fecha, tipo, bruto, neto, comision, limpieza)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS temporadas (
                mes  INTEGER PRIMARY KEY,
                tipo TEXT CHECK(tipo IN ('alta','media','baja')) DEFAULT 'media'
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS config (
                clave VARCHAR(100) PRIMARY KEY,
                valor TEXT
            )
        """)

        cur.execute("SELECT COUNT(*) FROM temporadas")
        if cur.fetchone()[0] == 0:
            defaults = [
                (1,'alta'),(2,'alta'),(3,'media'),(4,'media'),
                (5,'baja'),(6,'baja'),(7,'media'),(8,'media'),
                (9,'baja'),(10,'baja'),(11,'media'),(12,'alta')
            ]
            cur.executemany("INSERT INTO temporadas VALUES (%s, %s)", defaults)

        cur.execute("""
            INSERT INTO config (clave, valor) VALUES ('chat_huespedes', '0')
            ON CONFLICT (clave) DO NOTHING
        """)

        conn.commit()
        print("[DB] Base de datos inicializada correctamente.")
    except Exception as e:
        conn.rollback()
        print(f"[DB] Error en init_db: {e}")
        raise
    finally:
        cur.close()
        _release(conn)


def _leer(sql, params, uno):
    """### CAMBIO AQUÍ ### lectura con un reintento: si la conexión se había cortado (la base se durmió
    o se reinició), se descarta y se prueba una vez más con otra, en vez de mostrar un error."""
    for intento in range(2):
        conn = get_db()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, params)
            out = cur.fetchone() if uno else cur.fetchall()
            cur.close()
            _release(conn)
            if uno:
                return dict(out) if out else None
            return [dict(r) for r in out]
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            try:
                _get_pool().putconn(conn, close=True)
            except Exception:
                pass
            if intento == 1:
                raise
        except Exception:
            _rollback(conn)
            _release(conn)
            raise


def query(sql, params=()):
    return _leer(sql, params, False)


def query_one(sql, params=()):
    return _leer(sql, params, True)


def execute(sql, params=()):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        try:
            lid = cur.fetchone()[0]
        except Exception:
            lid = None
        cur.close()
        return lid
    except Exception:
        _rollback(conn)
        raise
    finally:
        _release(conn)


def execute_many(sql, params_list):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.executemany(sql, params_list)
        conn.commit()
        cur.close()
    except Exception:
        _rollback(conn)
        raise
    finally:
        _release(conn)
