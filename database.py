# database.py
import os
import psycopg2
import psycopg2.extras
import psycopg2.pool

DATABASE_URL = os.getenv("DATABASE_URL")

# ### CAMBIO AQUÍ ### — lazy init: el pool se crea solo cuando se necesita
_pool = None

def _get_pool():
    global _pool
    if _pool is None:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise RuntimeError(
                "DATABASE_URL no está configurada. "
                "Añadila en las variables de entorno de Render (o en .env local)."
            )
        _pool = psycopg2.pool.SimpleConnectionPool(1, 10, url)
    return _pool


_con_hora_ar = set()   # ### CAMBIO AQUÍ ###


def get_db():
    conn = _get_pool().getconn()
    # ### CAMBIO AQUÍ ### — la base también trabaja en hora de Buenos Aires (CURRENT_DATE, fechas guardadas)
    if id(conn) not in _con_hora_ar:
        try:
            cur = conn.cursor()
            cur.execute("SET TIME ZONE 'America/Argentina/Buenos_Aires'")
            conn.commit()
            cur.close()
            _con_hora_ar.add(id(conn))
        except Exception:
            conn.rollback()
    return conn

# Alias para compatibilidad con asistente_route.py y exportar_routes.py
def get_db_connection():
    return get_db()


def _release(conn):
    _get_pool().putconn(conn)

def release_db(conn):
    """Alias público de _release para blueprints externos."""
    _release(conn)


def init_db():
    conn = get_db()
    cur = conn.cursor()
    try:
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


def query(sql, params=()):
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)   # ### CAMBIO AQUÍ ### — siempre se devuelve al pool


def query_one(sql, params=()):
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        row = cur.fetchone()
        cur.close()
        return dict(row) if row else None
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


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
        conn.rollback()
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
        conn.rollback()
        raise
    finally:
        _release(conn)
