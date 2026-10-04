import os
import psycopg2
import psycopg2.extras
import psycopg2.pool

DATABASE_URL = os.getenv("DATABASE_URL")

# Pool minimo para no abrir una conexion por request en produccion
_pool = psycopg2.pool.SimpleConnectionPool(1, 10, DATABASE_URL)


def get_db():
    return _pool.getconn()


def _release(conn):
    _pool.putconn(conn)


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS propiedades (
            id               SERIAL PRIMARY KEY,
            nombre           TEXT NOT NULL,
            direccion        TEXT,
            barrio           TEXT,
            tipo             TEXT CHECK(tipo IN ('depto','casa')),
            ambientes        INTEGER,
            capacidad        INTEGER,
            precio_base      REAL DEFAULT 0,
            costo_expensas   REAL DEFAULT 0,
            costo_servicios  REAL DEFAULT 0,
            costo_limpieza   REAL DEFAULT 0,
            costo_comision   REAL DEFAULT 0,
            info_huespedes   TEXT DEFAULT '',
            creada_en        TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reservas (
            id                  SERIAL PRIMARY KEY,
            propiedad_id        INTEGER REFERENCES propiedades(id),
            codigo_confirmacion TEXT UNIQUE,
            fecha_inicio        TEXT,
            fecha_fin           TEXT,
            noches              INTEGER,
            ingreso_bruto       REAL DEFAULT 0,
            comision_airbnb     REAL DEFAULT 0,
            limpieza            REAL DEFAULT 0,
            ingreso_neto        REAL DEFAULT 0,
            anticipacion_dias   INTEGER,
            fuente              TEXT DEFAULT 'csv',
            importado_en        TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
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
            cargado_en   TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
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
            creada_en    TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS informes (
            id           SERIAL PRIMARY KEY,
            titulo       TEXT,
            fecha_desde  TEXT,
            fecha_hasta  TEXT,
            propiedad_id INTEGER,
            contenido    TEXT NOT NULL,
            creado_en    TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS temporadas (
            mes  INTEGER PRIMARY KEY,
            tipo TEXT CHECK(tipo IN ('alta','media','baja')) DEFAULT 'media'
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

    conn.commit()
    cur.close()
    _release(conn)
    print("[DB] Base de datos inicializada correctamente.")


def query(sql, params=()):
    conn = get_db()
    # RealDictCursor devuelve filas como dicts, igual que sqlite3.Row
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    _release(conn)
    return [dict(r) for r in rows]


def query_one(sql, params=()):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, params)
    row = cur.fetchone()
    cur.close()
    _release(conn)
    return dict(row) if row else None


def execute(sql, params=()):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    # RETURNING id debe estar en el SQL para recuperar el id insertado en Postgres
    try:
        lid = cur.fetchone()[0]
    except Exception:
        lid = None
    cur.close()
    _release(conn)
    return lid


def execute_many(sql, params_list):
    conn = get_db()
    cur = conn.cursor()
    cur.executemany(sql, params_list)
    conn.commit()
    cur.close()
    _release(conn)
