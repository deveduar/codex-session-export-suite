# Codex Extension Exporter

Herramienta en Python para extraer y limpiar las conversaciones locales de la extensión de Codex en VS Code, convirtiéndolas en archivos Markdown, JSONL o JSON. Funciona en Linux y Windows.

---

## Instalación

### Linux

```bash
python3 cli.py --help
pip install -e .
codex_export --help
```

### Windows

```powershell
py cli.py --help
py -m pip install -e .
codex_export --help
```

> **Importante:** `py codex_export` no funciona porque `py` espera un archivo `.py` o un módulo con `-m`. Usa `codex_export` después de instalarlo, `py cli.py ...` o `py -m cli ...`.

---

## Uso

El primer argumento puede ser:

- la carpeta raíz de Codex (`~/.codex`)
- la carpeta `sessions`
- una subcarpeta de año/mes (`sessions/2026/10`)
- un archivo `.jsonl` concreto

```bash
# Carpeta raíz de Codex
codex_export ~/.codex --preset transcript

# Solo una sesión concreta
codex_export ~/.codex/sessions/2026/10/30/rollout-2026-10-30T12-00-00-abc.jsonl

# Subcarpeta de un mes
codex_export ~/.codex/sessions/2026/10 --preset notes

# Windows
codex_export "%USERPROFILE%\.codex" --preset transcript
codex_export "%USERPROFILE%\.codex" --preset transcript -o "%USERPROFILE%\codex_exports"
codex_export "%USERPROFILE%\.codex\sessions\2026\10\30\rollout-2026-10-30T12-00-00-abc.jsonl"

# Sin instalar nada
python3 cli.py ~/.codex --preset transcript
py cli.py "%USERPROFILE%\.codex" --preset transcript
```

El directorio de salida se indica con `-o/--output` y admite `~` y variables de entorno:

```bash
codex_export ~/.codex -o ./mis_exportaciones
codex_export ~/.codex -o "%USERPROFILE%\codex_exports"
```

### Presets disponibles

| Preset | Descripción | Salida actual |
|--------|-------------|---------------|
| `transcript` | Conversación completa en Markdown, en orden cronológico | `.md` |
| `memory` | Corpus JSONL para RAG/alimentar otra IA | `.jsonl` |
| `digest` | Resúmenes truncados | `.md` |
| `faithful` | Archivo JSON lossless por sesión | `.json` |
| `notes` | Lectura con tool output truncado | `.md` |
| `conversation` | Solo diálogo, sin tools ni reasoning | `.md` |
| `prompts` | Solo tus prompts | `.md` (solo USER) |
| `review` | Log legible sin reasoning | `.md` |
| `archive` | Backup completo (pendiente de formato propio) | `.md` |
| `quick` | Sesión raw (pendiente de formato propio) | `.md` |
| `study` | Log + corpus (pendiente de formato propio) | `.md` |
| `rag` | Una línea por sesión (pendiente de formato propio) | `.md` |

`archive`, `quick`, `study` y `rag` todavía producen Markdown; su formato específico queda pendiente.

```bash
codex_export --list-presets
```

---

## Configuración

El archivo `codex_export.ini` permite cambiar los valores por defecto:

```ini
[codex]
# Carpeta raíz, sessions, subcarpeta o .jsonl
dir = ~/.codex
# Windows: dir = %USERPROFILE%\.codex

[output]
dir = ./codex_exports

[export]
preset = transcript
# user, assistant o both. Vacío = sin filtro.
role =
# Truncar a N caracteres. Vacío = sin truncar.
truncate =
timestamps = true
```

Precedencia: **argumentos de la CLI > archivo de configuración > valores internos**.

Ubicaciones que se buscan automáticamente:

1. `./codex_export.ini` en el directorio actual.
2. Configuración por usuario:
   - Windows: `%APPDATA%\codex_exporter\config.ini`
   - Linux: `~/.config/codex_exporter/config.ini`

También puedes indicar un archivo concreto:

```bash
codex_export --config ./mi_config.ini
```

Los valores admiten `~`, `$HOME` y `%USERPROFILE%`. En INI, escribe las rutas de Windows sin comillas.

---

## Opciones de línea de comandos

```
posicionales:
  codex_dir             Carpeta Codex, carpeta sessions, subcarpeta o .jsonl

opciones:
  -h, --help            Muestra la ayuda
  -o, --output DIR      Directorio de salida (default: config o ./codex_exports)
  --config FILE         Archivo INI de configuración
  -p, --preset PRESET   Preset de exportación
  --products NAME...    transcript, memory, digest, faithful o cualquier preset
  --role ROLE           user, assistant o both
  --truncate N          Trunca el texto a N caracteres (0 = sin truncar)
  --no-timestamps       Oculta los timestamps
  --dry-run             Muestra lo que haría sin escribir archivos
  --list-presets        Lista productos y presets
  --version             Muestra la versión
```

Se pueden generar varios productos a la vez:

```bash
codex_export ~/.codex --products transcript memory faithful
```

Si pides varios productos que generan Markdown, se añade el nombre del producto al archivo para evitar que se sobrescriban (por ejemplo `notes_....md` y `prompts_....md`).

---

## Ubicación de datos de Codex

Linux:

```
~/.codex/
├── sessions/
│   └── 2026/10/27/rollout-....jsonl
├── archived_sessions/
├── session_index.jsonl
└── config.toml
```

Windows:

```
%USERPROFILE%\.codex\
├── sessions\
│   └── 2026\10\27\rollout-....jsonl
├── archived_sessions\
├── session_index.jsonl
└── config.toml
```

Por ahora solo se leen las sesiones de `sessions/`. Las conversaciones archivadas en `archived_sessions/` no se procesan automáticamente, aunque puedes pasar esa carpeta o un archivo concreto como primer argumento.

---

## Uso en Windows y Linux sobre el mismo repositorio

No hay conflicto por el código ni por la configuración por defecto:

- `codex_exports/` está en `.gitignore`, así que no se sube al repositorio.
- La salida por defecto es `./codex_exports` relativa al directorio desde el que ejecutes el comando.
- Los nombres de archivo se sanean para evitar caracteres inválidos de Windows.

Si compartes la misma carpeta de salida entre Windows y Linux y exportas la misma sesión en ambos, el archivo se sobrescribe porque el nombre es determinista. Para evitarlo, usa una salida distinta en cada sistema:

```bash
codex_export ~/.codex -o ./codex_exports/linux
codex_export "%USERPROFILE%\.codex" -o "%USERPROFILE%\codex_exports\windows"
```

---

## Estructura del repositorio

```
codex_extension_exporter/
├── cli.py              # Punto de entrada y CLI
├── config.py           # Lectura de codex_export.ini
├── extract.py          # Parsing de JSONL y filtrado
├── products.py         # Productos y presets
├── output.py           # Formatos Markdown, JSONL y JSON
├── codex_export.ini    # Configuración por defecto
├── pyproject.toml
└── README.md
```

---

## Licencia

Consulta el archivo `private.txt` para detalles de configuración privada.
