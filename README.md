# Codex Extension Exporter

Herramienta en Python para extraer y limpiar las conversaciones locales de la extensión de Codex en VS Code (Linux Mint), convirtiéndolas en archivos **Markdown (`.md`)** listos para usar en tus herramientas de notas.

---

## 📦 Instalación

```bash
# Desde la raíz del repositorio
python3 cli.py --help
python3 cli.py --preset transcript

# O usando el módulo (después de instalar con pip)
pip install -e .
codex_export
```

---

## 📁 Estructura del Repositorio

```
/codex_extension_exporter/
│   ├── __init__.py
│   ├── cli.py           # Punto de entrada principal
│   ├── extract.py       # Lógica core: extracción y filtrado
│   ├── products.py      # Productos y presets de exportación
│   └── output.py        # Formato de salida (Markdown, JSONL, JSON)
├── .gitignore
├── pyproject.toml
├── README.md
├── private.txt
├── x/
└── archive_olds/
```

---

## 🚀 Uso CLI

```bash
# Modo básico - extraer transcripciones completas
codex_export ~/.codex

# Con preset de exportación
codex_export ~/.codex --preset transcript
codex_export ~/.codex --preset memory
codex_export ~/.codex --preset digest
codex_export ~/.codex --preset faithful
codex_export ~/.codex --preset notes
codex_export ~/.codex --preset conversation
codex_export ~/.codex --preset prompts
codex_export ~/.codex --preset rag
codex_export ~/.codex --preset archive
codex_export ~/.codex --preset quick
codex_export ~/.codex --preset study
codex_export ~/.codex --preset review

# Con opciones adicionales
codex_export ~/.codex --preset transcript --role user
codex_export ~/.codex --preset notes --truncate 500
codex_export ~/.codex --preset transcript --no-timestamps

# Lista de presets disponibles
codex_export --list-presets

# Directorio de salida personalizado
codex_export ~/.codex -o ./mis_exportaciones
```

### Presets Disponibles

| Preset | Descripción | Formato |
|--------|-------------|---------|
| `transcript` | Conversación completa en Markdown con roles USER/CODEX | `.md` |
| `memory` | Corpus JSONL para RAG/alimentar otra IA | `.jsonl` |
| `digest` | Resúmenes truncados ( Knowledge arc ) | `.md` |
| `faithful` | Archivo JSON lossless por sesión (todos los mensajes) | `.json` |
| `archive` | Backup completo con tool outputs | `.json` |
| `quick` | Sesión raw lossless, un archivo JSONL por sesión | `.jsonl` |
| `study` | Registro legible + corpora buscable | `.md` + `.jsonl` |
| `review` | Regreso legible sin reasoning + raw session | `.md` + `.json` |
| `notes` | Lectura pura, tool output truncado ~500 chars | `.md` |
| `conversation` | Diálogo solo, sin tools ni reasoning | `.md` |
| `prompts` | Solo tus prompts, sin respuestas ni tools | `.md` (solo USER) |
| `rag` | Una línea por sesión - tokens, asks, tools, digests | `.jsonl` |

---

## ⚙️ Opciones de Línea de Comandos

```
posicionales:
  codex_dir       Ruta al directorio Codex (default: ~/.codex)

opciones:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        Output directory (default: ./codex_exports)
  -p PRESET, --preset PRESET
                        Export preset: transcript, memory, digest, faithful,
                        notes, conversation, prompts, rag, archive, quick,
                        study, review, digest_only
  --products PRODUCTS   Custom products: transcript, memory, digest, faithful
  --role ROLE           Force role filter: user, assistant, or both
  --truncate N          Truncate tool output to N characters
  --no-timestamps       Hide timestamps in output
  --dry-run             Show what would be extracted without writing files
  --list-presets        List available export presets
  --version             show program's version number and exit
```

---

## 📂 Ubicación de Datos de Codex

La extensión almacena los historiales de chat locales en:

* **Directorio principal:** `~/.codex/`
* **Archivos de sesión (Rollouts):** `~/.codex/sessions/**/*.jsonl`

Ejemplo de estructura encontrada:
```
.codex/
├── sessions/
│   └── 2026/
│        └── 10/
│            └── rollout-2026-10-27T21-16-50-01a17f02-2ab4-7aa2-bfeb-1531a3e4f200.jsonl
├── session_index.jsonl
├──*.sqlite (bases de datos internas)
└── config.toml
```

---

## 🏗️ Arquitectura Interna

El nuevo `codex_exporter` es un paquete modular con separación de responsabilidades:

1. **extract.py** - Parsing de JSONL, detección de roles, filtrado de ruido
2. **products.py** - Configuraciones de producto y presets ("four products" matrix)
3. **output.py** - Formateo a Markdown, JSONL, JSON
4. **cli.py** - Interfaz de línea de comandos con argparse

Los presets siguen la matriz de "cuatro productos" definida en el diseño:
- **transcript**: conversación completa (texto + tools + patches + digests)
- **memory**: corpus.jsonl — una línea JSON por raíz de sesión
- **digest**: solo los digests de contexto compactado
- **faithful**: archivo nativo JSON lossless por sesión

---

## 📜 Licencis

Consulta el archivo `private.txt` para detalles de configuración privada.