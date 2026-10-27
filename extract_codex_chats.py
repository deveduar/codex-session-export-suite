import os
import json
from pathlib import Path

def extract_content(obj):
    """Extrae recursivamente todo el texto útil de diccionarios, listas y estructuras anidadas."""
    texts = []
    if isinstance(obj, str):
        if obj.strip():
            texts.append(obj.strip())
    elif isinstance(obj, dict):
        # Claves comunes donde suele residir el contenido real en logs de agentes de IA
        for key in ['content', 'text', 'message', 'prompt', 'completion', 'value', 'body', 'output', 'input']:
            if key in obj:
                texts.extend(extract_content(obj[key]))
        
        # Si tiene 'parts' (común en formatos multimodales o bloques de texto)
        if 'parts' in obj:
            texts.extend(extract_content(obj['parts']))
            
        # Si no encontró claves directas pero tiene otros valores, buscar en todo el dict
        if not texts:
            for k, v in obj.items():
                if k not in ['timestamp', 'time', 'id', 'uuid', 'type', 'role']:
                    texts.extend(extract_content(v))
                    
    elif isinstance(obj, list):
        for item in obj:
            texts.extend(extract_content(item))
            
    return texts

def parse_codex_sessions(codex_dir="~/.codex", output_dir="./codex_markdown_exports"):
    codex_path = Path(codex_dir).expanduser()
    output_path = Path(output_dir).expanduser()
    output_path.mkdir(parents=True, exist_ok=True)

    sessions_dir = codex_path / "sessions"
    if not sessions_dir.exists():
        print(f"[!] No se encontró la carpeta de sesiones en: {sessions_dir}")
        return

    jsonl_files = list(sessions_dir.glob("**/*.jsonl"))
    if not jsonl_files:
        print("[!] No se encontraron archivos .jsonl en las sesiones.")
        return

    print(f"[*] Se encontraron {len(jsonl_files)} archivos de sesión. Procesando a fondo...")

    for file_path in jsonl_files:
        md_lines = [f"# Historial Codex: `{file_path.name}`\n\n---\n\n"]
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        
                        role = data.get('role') or data.get('type') or data.get('author') or data.get('event') or 'intercambio'
                        timestamp = data.get('timestamp') or data.get('time') or ''
                        
                        # Extraer todo el contenido textual anidado
                        extracted_texts = extract_content(data)
                        
                        # Filtrar duplicados exactos manteniendo el orden
                        unique_texts = []
                        seen = set()
                        for t in extracted_texts:
                            # Evitar repetir únicamente el nombre del rol si sale suelto
                            if t and t not in seen and t.lower() != str(role).lower():
                                seen.add(t)
                                unique_texts.append(t)
                        
                        if unique_texts:
                            md_lines.append(f"### � [{role.upper()}] {f'*(<span>{timestamp}</span>)*' if timestamp else ''} (Línea {line_num})\n\n")
                            for text in unique_texts:
                                md_lines.append(f"{text}\n\n")
                            md_lines.append("---\n\n")
                        else:
                            # Respaldo: si es un evento técnico puro sin texto, mostrar JSON limpio colapsable
                            clean_data = {k: v for k, v in data.items() if v}
                            if clean_data:
                                md_lines.append(f"<details>\n<summary><b>[Evento técnico / {role}] (Línea {line_num})</b></summary>\n\n```json\n{json.dumps(clean_data, ensure_ascii=False, indent=2)}\n```\n\n</details>\n\n---\n\n")

                    except json.JSONDecodeError:
                        continue
            
            # Guardar el archivo Markdown resultante
            relative_parts = file_path.relative_to(sessions_dir)
            output_filename = f"session_{'_'.join(relative_parts.parts).replace('.jsonl', '')}.md"
            output_file = output_path / output_filename
            
            with open(output_file, 'w', encoding='utf-8') as out_f:
                out_f.writelines(md_lines)
                
            print(f"[+] Archivo exportado con éxito: {output_file.name}")
            
        except Exception as e:
            print(f"[!] Error procesando el archivo {file_path.name}: {e}")

    print(f"\n¡Extracción completa! Revisa tu contenido en la carpeta: {output_path.absolute()}")

if __name__ == "__main__":
    parse_codex_sessions()