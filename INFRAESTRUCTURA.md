# PalermitanHost — Guía de infraestructura

Pasos para dejar el sistema de Adriano funcionando de forma segura y sin depender de nadie.
Cada paso dice **dónde** se hace y **qué** copiar. Las claves nunca se pegan en un chat: van solo en Render o en GitHub.

---

## 1. Base de datos en Neon (gratis y sin vencimiento)

La base de datos gratis de Render **se borra a los 30 días**. Neon tiene un plan gratis que no vence.

1. Entrá a <https://neon.tech> y creá una cuenta (podés usar la de Google de Adriano).
2. **Create project** → nombre `palermitanhost` → región **AWS São Paulo** (la más cerca de Buenos Aires).
3. En el panel, **Connect** → copiá la *connection string* que empieza con `postgresql://` y termina con `?sslmode=require`.
4. En Render → servicio web → **Environment** → variable `DATABASE_URL` → pegá la de Neon → **Save**.
5. Render reinicia solo. El sistema crea todas las tablas la primera vez que arranca.

**Si ya había datos en la base vieja de Render**, antes del paso 4:

```
pg_dump "URL_EXTERNA_DE_RENDER" -Fc -f respaldo.dump
pg_restore --no-owner -d "URL_DE_NEON" respaldo.dump
```

## 2. Copia de seguridad automática (ya está armada)

El archivo `.github/workflows/respaldo.yml` hace una copia cifrada **todos los lunes** y una **anual** que no se borra nunca.
Solo hay que cargar dos secretos en GitHub → repositorio → **Settings → Secrets and variables → Actions**:

| Secreto | Qué poner |
|---|---|
| `DATABASE_URL_EXTERNA` | La misma URL de Neon del paso 1 |
| `CLAVE_RESPALDO` | Una frase larga inventada. **Guardala**: sin ella la copia no se abre |

**Probá que se puede restaurar** (una vez, para estar seguros):

1. GitHub → **Actions → Copia de seguridad → Run workflow**.
2. Cuando termina, descargá el archivo `respaldo-...` de esa corrida.
3. En tu compu:

```
gpg --batch --passphrase "TU_CLAVE" -o respaldo.dump -d respaldo-FECHA.dump.gpg
pg_restore --list respaldo.dump
```

Si `pg_restore --list` muestra la lista de tablas, la copia está bien.

## 3. Aviso si el sistema se cae (UptimeRobot, gratis)

1. Entrá a <https://uptimerobot.com> y creá una cuenta.
2. **Add New Monitor** → tipo **HTTP(s)** → URL: `https://TU-APP.onrender.com/salud?db=1` → cada **5 minutos**.
3. En *Alert contacts* poné tu mail (y el de Adriano si querés).

Si la página o la base de datos dejan de responder, te llega un mail. Además, el chequeo cada 5 minutos evita que Render "duerma" el sistema.

## 4. Resumen diario por mail a las 9

**a) Una cuenta de Gmail para mandar** (puede ser una nueva, ej. `palermitanhost.avisos@gmail.com`):

1. Activá la **verificación en 2 pasos** de esa cuenta (Cuenta de Google → Seguridad).
2. Cuenta de Google → Seguridad → **Contraseñas de aplicaciones** → creá una llamada "PalermitanHost". Te da 16 letras.

**b) En Render → Environment**, agregá:

| Variable | Valor |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `465` |
| `SMTP_USER` | la cuenta de Gmail que manda |
| `SMTP_PASS` | las 16 letras de la contraseña de aplicación |
| `MAIL_PARA` | el mail de Adriano (y el tuyo, separados por coma) |
| `APP_URL` | `https://TU-APP.onrender.com` |

**c) Probalo:** en el sistema → **Más → Ajustes → Resumen diario por mail → Mandar uno de prueba ahora**.

**d) Que salga solo todos los días:** en <https://cron-job.org> (donde ya está la tarea de competencia) creá otra tarea:

- URL: `https://TU-APP.onrender.com/tareas/resumen`
- Horario: todos los días a las **9:00** (zona Buenos Aires)
- Avanzado → **Headers** → `X-Token` = el mismo valor de `TAREAS_TOKEN`

El día 1 de cada mes el resumen trae además **cómo fue el mes anterior**.

> **WhatsApp:** se puede agregar más adelante con la API de WhatsApp de Meta (como en Orvion Finanzas). Necesita un número verificado por Meta.

## 5. Aviso de errores con Sentry (opcional, gratis)

1. Entrá a <https://sentry.io> → creá una cuenta → **Create project** → plataforma **Flask**.
2. Copiá el **DSN** (empieza con `https://` y tiene `@` y `ingest.sentry.io`).
3. En Render → Environment → `SENTRY_DSN` = ese DSN.

Cuando algo falle te llega un mail con el error. El sistema **no manda** datos de huéspedes, cookies ni formularios.

## 6. Pruebas automáticas en cada `git push`

Las pruebas están en la carpeta `tests/` (más de 580 chequeos). Para que GitHub las corra solas en cada push,
creá a mano el archivo **`.github/workflows/pruebas.yml`** con este contenido (desde GitHub: **Add file → Create new file**):

```yaml
name: Pruebas
on:
  push:
  pull_request:
  workflow_dispatch:
jobs:
  pruebas:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_HOST_AUTH_METHOD: trust
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready --health-interval 5s --health-timeout 5s --health-retries 10
    env:
      PRUEBAS_OK: "1"
      PRUEBAS_DATABASE_URL: postgresql://postgres@localhost:5432/postgres
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: pip
      - run: pip install -r requirements.txt
      - name: Correr todas las pruebas
        run: python tests/correr.py
```

Después de cada push, en la pestaña **Actions**: verde = todo bien, se puede hacer *Manual Deploy*; rojo = algo se rompió, no deployar.

> Las pruebas **borran la base que usan**. Por eso solo corren con `PRUEBAS_OK=1` y una base en `localhost`; nunca contra Neon ni Render.

## 7. Usuarios de limpieza y co-anfitrión

Se crean desde **Más → Ajustes → Otros usuarios**. No hace falta tocar Render.
Quien limpia solo ve la lista de limpiezas; el co-anfitrión ve todo menos borrar datos y manejar usuarios.

## 8. Instalar en el celular

En el celular de Adriano: abrir el sistema →
- **Android (Chrome):** menú ⋮ → *Instalar app*.
- **iPhone (Safari):** Compartir → *Agregar a inicio*.

---

### Variables de entorno: resumen

| Variable | Obligatoria | Para qué |
|---|---|---|
| `DATABASE_URL` | Sí | Base de datos (Neon) |
| `SECRET_KEY`, `ADMIN_USER`, `ADMIN_PASS` | Sí | Seguridad y acceso |
| `GROQ_API_KEY` | Sí | Asistente IA |
| `TAREAS_TOKEN` | Para tareas automáticas | Competencia nocturna y resumen diario |
| `SERPAPI_API_KEY`, `TAVILY_API_KEY` | Opcional | Búsqueda de competencia |
| `SMTP_*`, `MAIL_PARA`, `APP_URL` | Para el resumen por mail | Paso 4 |
| `SENTRY_DSN` | Opcional | Paso 5 |
