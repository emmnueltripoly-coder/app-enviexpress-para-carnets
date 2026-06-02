# CLAUDE.md

**Propósito:** Memoria persistente del proyecto. Claude Code debe leer este archivo al inicio de CADA sesión antes de ejecutar cualquier tarea. Define reglas que NO se pueden romper.

---

## 1. Qué estamos construyendo

Sistema de control de asistencia y gestión de personal para empresa colombiana con certificación BASC. Sedes en Medellín, Cali, Bogotá y Barranquilla. 163 empleados.

**Funcionalidad (MVP):**

- Marcación de entrada/salida (QR dinámico + geocerca, tolerante a offline).
- Gestión de turnos.
- Horas extra.
- Novedades (incapacidades, permisos, vacaciones, problemas reportados desde la app).
- Panel web administrativo (RRHH/supervisor) que recibe y gestiona novedades.
- Notificación por email al reportar novedades.

**Fuera del MVP (pero la BD debe dejar la puerta abierta):** liquidación de nómina.

---

## 2. Stack tecnológico (NO cambiar sin aprobación)

- **Backend + Web Admin:** Python + Django + Django REST Framework (DRF).
- **Base de datos:** PostgreSQL 16+ (NO SQLite, ni siquiera en desarrollo: necesitamos triggers reales).
- **App móvil empleados:** React Native (Expo). Consume la API del backend Django.
- **Autenticación API:** JWT vía djangorestframework-simplejwt.
- **Panel admin:** Django Admin (nativo) para gestión interna RRHH/Admin.
- **Migraciones:** sistema de migraciones de Django + migraciones SQL crudas (RunSQL) para triggers.

---

## 3. REGLAS NO NEGOCIABLES (BASC + Ley 1581 Habeas Data)

Aplican a TODA tarea. Si una tarea las contradice, DETENTE y avisa.

- **Logs de auditoría inalterables (append-only).** Toda acción sensible (marcación, aprobación de novedad, cambio de turno, login, exportación de datos) se escribe en una tabla `audit_log` que SOLO permite INSERT. Prohibido UPDATE y DELETE — se fuerza con un trigger de PostgreSQL (vía migración RunSQL), no solo con código Python.
- **Marcaciones inmutables.** Un registro de marcación nunca se edita ni se borra. Una corrección es un NUEVO registro que referencia al anterior (patrón de reversión contable).
- **Habeas Data (Ley 1581).** Datos personales con acceso por rol. Registro de consentimiento del titular con fecha y versión de política. Capacidad de exportar y de anonimizar los datos de una persona bajo solicitud.
- **Trazabilidad temporal confiable.** Timestamps en UTC. `USE_TZ = True` en Django. En marcación offline se guardan DOS sellos: hora del dispositivo y hora de sincronización del servidor. Nunca se confía solo en el cliente.
- **Rol Auditor read-only.** Un rol que lee todo el historial y los logs, sin poder modificar nada.
- **Sin borrado físico.** Ninguna entidad de negocio se borra; se marca inactiva (soft-delete) salvo solicitud legal de supresión de datos personales.

---

## 4. Roles de usuario

| Rol | Permisos |
| --- | --- |
| **Empleado** | Marcar entrada/salida, reportar novedades, ver su propio historial. |
| **Supervisor** | Ver/gestionar su equipo y sede, aprobar novedades de primer nivel. |
| **RRHH** | Gestión global de novedades, turnos, horas extra, reportes. |
| **Auditor** | Solo lectura de todo el historial y logs. |
| **Admin** | Configuración del sistema, gestión de usuarios y sedes. |

**Implementación:** modelo de usuario personalizado (`AbstractUser`) con campo `rol`, combinado con Grupos/permisos de Django.

---

## 5. Cómo trabajar en este proyecto (metodología)

- **Una micro-tarea a la vez.** Cada prompt ejecuta UN hito atómico. No adelantarse a hitos futuros.
- **No romper lo existente.** Antes de modificar un archivo, leerlo. Cambios aditivos siempre que sea posible.
- **Cada tarea termina con:** migraciones aplicadas, un test mínimo que pasa, y un resumen de lo creado.
- **Si falta una decisión de diseño, PREGUNTAR, no asumir.**
- **Nunca poner secretos en el código.** Credenciales y `SECRET_KEY` van en variables de entorno (`.env`), nunca commiteadas.

---

## 6. Roadmap de hitos (orden de ejecución)

- **Hito 0 — Fundación:** proyecto Django + DRF + conexión PostgreSQL, app `auditoria` con modelo `AuditLog`, trigger SQL append-only, `AuditService`. ← EMPEZAMOS AQUÍ
- **Hito 1 — Identidad:** modelos Empresa/Sede/Empleado, usuario personalizado con rol, consentimiento Habeas Data.
- **Hito 2 — Autenticación y permisos:** JWT (simplejwt), permisos por rol, registro en `audit_log` de cada login.
- **Hito 3 — Núcleo de marcación:** QR dinámico, geocerca por sede, constraint anti-doble-marcación.
- **Hito 4 — Offline sync:** cola local en la app + endpoint de sincronización con doble timestamp.
- **Hito 5 — Turnos y horas extra.**
- **Hito 6 — Novedades + notificación email + recepción en panel.**
- **Hito 7 — Panel admin web (Django Admin afinado) + rol Auditor read-only.**
- **Hito 8 — Reportes y exportación (apta inspección Min. Trabajo / BASC).**

---

## 7. Riesgos técnicos (mitigar desde el diseño)

- **Concurrencia en marcación:** pico ~40-50/sede en 10-15 min. Mitigación: transacción atómica (`select_for_update` / constraint único `(empleado, fecha, tipo)`). No requiere colas en MVP.
- **Fraude de marcación:** QR estático es vulnerable. Mitigación: QR rotativo (30-60s) validado en servidor + geocerca.
- **Fraude offline:** hora del dispositivo manipulable. Mitigación: doble timestamp + ventana de tolerancia + flag auditable de "marcación offline".
- **Multi-ciudad / zona horaria:** Colombia es UTC-5 sin horario de verano; guardar siempre en UTC evita problemas.
- **PostgreSQL obligatorio:** SQLite no soporta los triggers que exige BASC. Usar Postgres desde el día uno.
