# � Codex Extension Exporter

Herramienta en Python para extraer y limpiar las conversaciones locales de la extensión de Codex en VS Code (Linux Mint), convirtiéndolas en archivos **Markdown (`.md`)** listos para usar en tus herramientas de notas (Obsidian, Notion, etc.).

---

## � Ubicación de los Datos

La extensión almacena los historiales de chat locales en tu sistema operativo en la siguiente ruta oculta:

* **Directorio principal:** `~/.codex/`
* **Archivos de sesión (Rollouts):** `~/.codex/sessions/**/*.jsonl`

---

## ✨ Características Principales

* **Filtro de Ruido:** Elimina telemetría interna, contadores de tokens, hashes y eventos del sistema.
* **Formato Limpio:** Estructura automáticamente el contenido diferenciando claramente entre el **USUARIO** y el **ASISTENTE (CODEX)**.
* **Exportación por Sesión:** Genera un archivo `.md` independiente y ordenado por cada conversación.

---

## � Uso Rápido

1. Ubícate en la carpeta donde tienes tu script de extracción en la terminal de Linux Mint.
2. Ejecuta el script:
```bash
python3 extract_codex.py

```


3. Encuentra tus chats limpios organizados dentro de la carpeta generada (por ejemplo, `./codex_sesiones_limpias`).

  
## �️ Arquitectura de Datos de Codex (Base de Datos y Estructura)

Para futuras mejoras y optimizaciones del script de extracción, esta es la radiografía exacta de cómo la extensión de Codex organiza la información localmente en `~/.codex/`:

### 1. Archivos de Sesión (Rollouts)

* **Ruta:** `~/.codex/sessions/**/*.jsonl`
* **Descripción:** Archivos de texto en formato JSON Lines (`.jsonl`). Son la **fuente de verdad** donde se almacena el flujo cronológico completo de los chats, payloads, mensajes de usuario y respuestas del agente.

### 2. Bases de Datos SQLite (`~/.codex/*.sqlite`)

* **`thread_history_1.sqlite`** (Base de datos central de historiales):
* Tabla `thread_turns`: Almacena metadatos de los turnos de conversación (IDs de hilo, estados, marcas de tiempo, y desplazamientos en bytes que apuntan a los archivos de rollout).
* Tabla `thread_items`: Contiene los elementos atómicos asociados a cada hilo de conversación.
* Otras tablas de soporte: `_sqlx_migrations`, `thread_history_projection_state`, `thread_realtime_items`.


* **`state_5.sqlite`**: Gestiona estados de migración, recibos de lectura de hilos y secciones.
* **`memories_1.sqlite`**: Almacena el progreso de consolidación de memoria del agente.
* **`logs_2.sqlite`**: Registros de diagnóstico y depuración interna.
* **`goals_1.sqlite` y `queue_1.sqlite**`: Control de objetivos activos y colas de tareas operativas de la extensión.

---

## �️ Resumen de Problemas y Resoluciones en este Chat

* **Problema:** La primera versión del script solo extraía metadatos superficiales (`session_meta`) y omitía el contenido del chat.
* **Resolución:** Se implementó una función de búsqueda recursiva de texto dentro de estructuras JSON anidadas.


* **Problema:** El volcado de datos incluía demasiada "basura técnica" (telemetría, contadores de tokens, hashes y eventos internos).
* **Resolución:** Se creó una lista negra de tipos de eventos y claves técnicas a ignorar sistemáticamente.


* **Problema:** Los archivos `.jsonl` devolvían vacíos al buscar claves rígidas como `role: 'user'` debido a la dinámica interna de Codex.
* **Resolución:** Se cambió el enfoque hacia una exploración dinámica de payloads (`agent_message`, `user_message`) y un análisis estructural de los rollouts.


* **Problema:** Error en SQLite por intentar consultar una columna inexistente (`turn_index` en `thread_turns`).
* **Resolución:** Se incorporó introspección dinámica de bases de datos mediante `PRAGMA table_info()` para detectar columnas reales en lugar de hardcodearlas.


* **Problema:** `thread_turns` resultó ser solo una tabla de índices y offsets, no de contenido de texto directo.
* **Resolución:** Se validó que el texto conversacional puro reside de forma fiable en los archivos físicos de rollout `.jsonl`, optimizando la lectura directa de estos.