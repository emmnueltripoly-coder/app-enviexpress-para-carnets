# Guía de despliegue en producción
## Backend Django → Render  +  PostgreSQL → Supabase  +  Storage → Supabase Storage

**Sistema:** Control de asistencia Enviexpress Logística  
**Stack:** Python / Django 5.2 · PostgreSQL 16 · Render (web service) · Supabase (BD + Storage)  
**Tiempo estimado:** 30–45 minutos la primera vez.

---

## Resumen de pasos

```
1. Crear proyecto en Supabase (BD + bucket privado)
2. Crear servicio web en Render (conectado al repositorio)
3. Configurar todas las variables de entorno en Render
4. Hacer el primer despliegue (Render ejecuta build.sh automáticamente)
5. Verificar que el panel admin funciona
```

---

## 1. Supabase — Base de datos PostgreSQL

### 1.1 Crear proyecto
1. Ir a [supabase.com](https://supabase.com) → **New project**.
2. Elegir la organización y región (ej. South America São Paulo si está disponible, o US East).
3. Anotar la **contraseña de base de datos** que se genera (se necesita en el paso 3).

### 1.2 Obtener la DATABASE_URL
1. En el proyecto: **Project Settings → Database → Connection string → URI**.
2. Copiar la URL. Tiene el formato:
   ```
   postgresql://postgres.[project-id]:[password]@aws-0-us-east-1.pooler.supabase.com:6543/postgres
   ```
3. Esa URL usa el **connection pooler** (puerto 6543, modo transaction). Es la recomendada para servicios serverless/PaaS.

> **Nota sobre CONN_MAX_AGE:** Con el pooler (puerto 6543) usar `CONN_MAX_AGE=0`.  
> Si prefiere la conexión directa (puerto 5432, sin pooler), puede usar `CONN_MAX_AGE=60`.

---

## 2. Supabase — Storage (para soportes de novedades)

Los soportes de incapacidades médicas son datos sensibles (Ley 1581). Se almacenan en un bucket **privado**; ningún archivo tiene URL pública. El acceso siempre pasa por la vista autenticada de Django.

### 2.1 Crear el bucket privado
1. En el proyecto Supabase: **Storage → New bucket**.
2. Nombre: `novedades-soportes` (o el que quiera; se configura en `SUPABASE_STORAGE_BUCKET`).
3. **IMPORTANTE: desmarcar "Public bucket"**. El bucket debe ser privado.

### 2.2 Obtener credenciales S3
1. Ir a **Project Settings → Storage → S3 Connection**.
2. Copiar:
   - **Access Key** → `SUPABASE_S3_ACCESS_KEY`
   - **Secret Key** → `SUPABASE_S3_SECRET_KEY`
   - **Endpoint URL** → `SUPABASE_S3_ENDPOINT_URL`  
     Formato: `https://<project-id>.supabase.co/storage/v1/s3`

> Si las credenciales S3 **no** están configuradas en Render, el sistema guarda los archivos localmente en el contenedor (efímero — se pierde al redesplegar). Configúrelas antes del primer uso en producción.

---

## 3. Render — Crear el servicio web

### 3.1 Crear el servicio
1. Ir a [render.com](https://render.com) → **New → Web Service**.
2. Conectar el repositorio de GitHub/GitLab.
3. Configurar:
   - **Name:** `enviexpress-asistencia`
   - **Branch:** `main` (o la rama de producción)
   - **Build Command:** `./build.sh`
   - **Start Command:**
     ```
     gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120 --log-level info
     ```
   - **Runtime:** Python 3.11
   - **Plan:** Free (o Starter para producción real)

### 3.2 Configurar variables de entorno
En **Settings → Environment**, agregar TODAS las siguientes variables. Los valores marcados con `⚠️` son obligatorios; los otros tienen valores por defecto razonables.

| Variable | Valor / Descripción |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings` |
| `DEBUG` | `False` |
| `SECRET_KEY` ⚠️ | Generar: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `ALLOWED_HOSTS` ⚠️ | `enviexpress-asistencia.onrender.com` (o el dominio real) |
| `DATABASE_URL` ⚠️ | URL copiada de Supabase (paso 1.2) |
| `CONN_MAX_AGE` | `0` (con pooler) ó `60` (conexión directa) |
| `CORS_ALLOWED_ORIGINS` | URL de la app móvil web / panel externo, si aplica |
| `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` |
| `EMAIL_HOST` | `smtp.gmail.com` o servidor de su proveedor de email |
| `EMAIL_PORT` | `587` |
| `EMAIL_HOST_USER` ⚠️ | Cuenta de correo del remitente |
| `EMAIL_HOST_PASSWORD` ⚠️ | Contraseña de app (Gmail) o API key |
| `EMAIL_USE_TLS` | `True` |
| `DEFAULT_FROM_EMAIL` | `no-responder@enviexpresslogistica.com` |
| `NOVEDADES_EMAILS` ⚠️ | Correos RRHH separados por coma |
| `SUPABASE_S3_ACCESS_KEY` ⚠️ | Del paso 2.2 |
| `SUPABASE_S3_SECRET_KEY` ⚠️ | Del paso 2.2 |
| `SUPABASE_STORAGE_BUCKET` | `novedades-soportes` (el nombre del bucket del paso 2.1) |
| `SUPABASE_S3_ENDPOINT_URL` ⚠️ | Del paso 2.2 |
| `SUPABASE_S3_REGION` | `us-east-1` |
| `DJANGO_SUPERUSER_USERNAME` ⚠️ | Nombre del primer usuario admin (ej: `admin`) |
| `DJANGO_SUPERUSER_PASSWORD` ⚠️ | Contraseña segura (mínimo 12 caracteres) |
| `DJANGO_SUPERUSER_EMAIL` | Email del admin |

### 3.3 Email con Gmail (cuenta de aplicación)
Si usa Gmail, debe generar una **contraseña de aplicación**:
1. Ir a **Google Account → Seguridad → Verificación en dos pasos** (activarla).
2. Ir a **Contraseñas de aplicaciones → Otra → Generarla**.
3. Copiar los 16 caracteres → `EMAIL_HOST_PASSWORD`.

---

## 4. Primer despliegue

Al hacer clic en **Deploy**, Render ejecuta `build.sh` automáticamente:
```bash
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py crear_superusuario_inicial
```

Las **migraciones incluyen los triggers de PostgreSQL** (append-only audit_log, inmutabilidad de marcaciones). Se ejecutan automáticamente con `migrate`.

### Verificar que funciona
1. Una vez desplegado, abrir `https://enviexpress-asistencia.onrender.com/admin/`.
2. Iniciar sesión con las credenciales del superusuario.
3. Verificar que el panel carga (Unfold con tema azul).
4. Cambiar la contraseña del admin después del primer login.

---

## 5. Despliegues posteriores

Render redespliega automáticamente al hacer push a la rama configurada. `build.sh` corre en cada despliegue:
- `collectstatic` es idempotente.
- `migrate` aplica solo migraciones pendientes.
- `crear_superusuario_inicial` no hace nada si el usuario ya existe.

---

## 6. Escalar (cuando el plan gratuito no sea suficiente)

- **Más tráfico:** aumentar `--workers` en el start command (1 worker ≈ 100 MB RAM).
- **Base de datos:** Supabase Pro permite más conexiones y backups automáticos.
- **Storage:** Supabase Pro incluye más almacenamiento para los soportes.

No es necesario cambiar ninguna línea de código para escalar. Solo variables de entorno y plan.

---

## 7. Seguridad de producción activa

Cuando `DEBUG=False`, Django activa automáticamente:

| Protección | Valor |
|---|---|
| `SECURE_SSL_REDIRECT` | `True` (HTTP → HTTPS) |
| `SECURE_PROXY_SSL_HEADER` | `HTTP_X_FORWARDED_PROTO: https` (compatible con proxy de Render) |
| `SESSION_COOKIE_SECURE` | `True` |
| `CSRF_COOKIE_SECURE` | `True` |
| `SECURE_HSTS_SECONDS` | `31536000` (1 año) |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `True` |
| `SECURE_CONTENT_TYPE_NOSNIFF` | `True` |
| `X_FRAME_OPTIONS` | `DENY` |

Verificable con: `python manage.py check --deploy` (debe retornar "no issues").

---

## 8. Comandos útiles post-despliegue

Ejecutar en la consola de Render (**Shell** tab del servicio):

```bash
# Crear usuario adicional RRHH
python manage.py shell -c "
from personal.models import Usuario
u = Usuario.objects.create_user('rrhh_coord', 'contraseña', rol=Usuario.Rol.RRHH, is_staff=True)
print('Creado:', u)
"

# Poblar festivos colombianos de un año
python manage.py poblar_festivos 2026

# Verificar estado del sistema
python manage.py check --deploy
```
