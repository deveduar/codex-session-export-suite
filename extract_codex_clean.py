import os
import json
from pathlib import Path

def extract_sessions_from_rollouts():
    codex_dir = Path("~/.codex").expanduser()
    sessions_dir = codex_dir / "sessions"
    output_dir = Path("./codex_sesiones_exactas").expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not sessions_dir.exists():
        print(f"[!] No se encontró la carpeta de sesiones: {sessions_dir}")
        return

    # Buscar todos los archivos .jsonl de rollout
    jsonl_files = list(sessions_dir.glob("**/*.jsonl"))
    print(f"[*] Se encontraron {len(jsonl_files)} archivos de sesión (rollouts). Procesando...")

    for file_path in jsonl_files:
        chat_turns = []
        print(f"\n[+] Analizando sesión: {file_path.name}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        
                        role = None
                        text = None

                        # Buscar estructuras comunes en los rollouts de Codex/VS Code
                        payload = data.get('payload') or data.get('message') or data
                        if isinstance(payload, dict):
                            role = payload.get('role') or payload.get('author') or data.get('role')
                            text = payload.get('content') or payload.get('text') or payload.get('prompt') or payload.get('completion')
                            
                            # Si el contenido viene en partes (listas)
                            if isinstance(text, list):
                                parts_text = []
                                for p in text:
                                    if isinstance(p, dict):
                                        parts_text.append(p.get('text', '') or p.get('value', ''))
                                    elif isinstance(p, str):
                                        parts_text.append(p)
                                text = "\n".join([pt for pt in parts_text if pt])
                                
                            # Si el contenido es un diccionario
                            elif isinstance(text, dict):
                                text = text.get('text') or text.get('value') or json.dumps(text, ensure_ascii=False)

                        # Filtrar y validar que sea texto conversacional real
                        if text and isinstance(text, str):
                            text_clean = text.strip()
                            # Omitir JSONs vacíos, hashes o líneas de sistema muy cortas
                            if len(text_clean) > 5 and not (text_clean.startswith('{') and text_clean.endswith('}')):
                                role_lower = str(role).lower() if role else ""
                                
                                if any(u in role_lower for u in ['user', 'usuario', 'human']):
                                    display_role = "� **USUARIO**"
                                elif any(a in role_lower for a in ['assistant', 'asistente', 'ai', 'gpt', 'codex', 'agent']):
                                    display_role = "� **ASISTENTE (CODEX)**"
                                else:
                                    display_role = "� **INTERVENCIÓN**"

                                chat_turns.append(f"### {display_role}\n\n{text_clean}\n\n---\n\n")

                    except json.JSONDecodeError:
                        continue

            # Guardar el archivo Markdown resultante para esta sesión
            if chat_turns:
                out_file = output_dir / f"sesion_{file_path.stem}.md"
                with open(out_file, 'w', encoding='utf-8') as out_f:
                    out_f.write(f"# Sesión Codex: `{file_path.name}`\n\n---\n\n")
                    out_f.writelines(chat_turns)
                print(f"    [+] ¡Exportado con éxito! {out_file.name} ({len(chat_turns)} mensajes extraídos)")
            else:
                print(f"    [-] No se encontraron mensajes en este archivo.")

        except Exception as e:
            print(f"    [!] Error leyendo el archivo {file_path.name}: {e}")

    print(f"\n¡Proceso finalizado! Revisa tus 2 sesiones exactas en la carpeta: {output_dir.absolute()}")

if __name__ == "__main__":
    extract_sessions_from_rollouts()