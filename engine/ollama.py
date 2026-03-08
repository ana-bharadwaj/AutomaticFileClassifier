import re
import requests


OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3.2" 


def is_ollama_available() -> bool:
    
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


def suggest_folder(filename: str,
                   ext: str,
                   size_bytes: int,
                   existing_folders: list[str]) -> str | None:
    try:
        import requests

        prompt = (
            "You are a file organizer assistant. "
            "Based ONLY on the filename and metadata provided, "
            "suggest the single best subfolder name to categorize this file. "
            "If an existing folder fits well, reuse it. "
            "Otherwise suggest a short, descriptive new folder name (2 words max). "
            "Reply with ONLY the folder name. No explanation, no punctuation.\n\n"
            f"Filename: {filename}\n"
            f"Extension: {ext}\n"
            f"Size: {_human_size(size_bytes)}\n"
            f"Existing subfolders: {', '.join(existing_folders) if existing_folders else 'none yet'}\n"
        )

        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,  
                    "num_predict": 20,   
                }
            },
            timeout=15
        )
        resp.raise_for_status()

        
        suggestion = resp.json().get("response", "").strip()

        
        suggestion = re.sub(r'[<>:"/\\|?*\n\r]', "", suggestion).strip()
        suggestion = suggestion[:50]  # cap length

        return suggestion if suggestion else None

    except Exception as e:
       
        print(f"[ollama] Unavailable or error: {e}")
        return None


def _human_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.0f} {unit}"
        size //= 1024
    return f"{size:.0f} TB"
