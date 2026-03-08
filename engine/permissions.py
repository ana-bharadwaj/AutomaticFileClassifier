import os
import json
import hashlib
from datetime import datetime
from pathlib import Path

STATE_FILE = os.path.expanduser("~/.downloads_sorter_state.json")

PENDING = "pending"
GRANTED = "granted"
DENIED  = "denied"


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {
        "permissions": {},
        "sorted_files": [],
        "session_stats": {}
    }


def save_state(state: dict):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)


def file_id(filepath: str) -> str:
   
    try:
        stat = os.stat(filepath)
        raw = f"{os.path.abspath(filepath)}:{stat.st_size}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
    except OSError:
        raw = os.path.abspath(filepath)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


def get_permission_status(filepath: str, state: dict) -> str:
    fid = file_id(filepath)
    entry = state["permissions"].get(fid)
    if entry is None:
        return PENDING
    return entry.get("status", PENDING)


def has_permission(filepath: str, state: dict) -> bool:
    return get_permission_status(filepath, state) == GRANTED


def is_denied(filepath: str, state: dict) -> bool:
    return get_permission_status(filepath, state) == DENIED


def grant_permission(filepath: str, state: dict) -> dict:
    fid = file_id(filepath)
    state["permissions"][fid] = {
        "status": GRANTED,
        "path": filepath,
        "filename": os.path.basename(filepath),
        "granted_at": datetime.now().isoformat()
    }
    save_state(state)
    return state


def deny_permission(filepath: str, state: dict) -> dict:
    fid = file_id(filepath)
    state["permissions"][fid] = {
        "status": DENIED,
        "path": filepath,
        "filename": os.path.basename(filepath),
        "denied_at": datetime.now().isoformat()
    }
    save_state(state)
    return state


def grant_all(filepaths: list, state: dict) -> dict:
    for fp in filepaths:
        grant_permission(fp, state)
    return state


def deny_all(filepaths: list, state: dict) -> dict:
    
    for fp in filepaths:
        deny_permission(fp, state)
    return state


def log_sorted_file(src: str, dest: str, category: str, group: str, state: dict):
    state["sorted_files"].append({
        "src": src,
        "dest": dest,
        "category": category,
        "group": group,
        "moved_at": datetime.now().isoformat()
    })
    save_state(state)


def get_session_summary(state: dict) -> dict:
    sorted_files = state.get("sorted_files", [])
    by_category = {}
    for entry in sorted_files:
        cat = entry.get("category", "Other")
        by_category[cat] = by_category.get(cat, 0) + 1
    return {
        "total": len(sorted_files),
        "by_category": by_category,
        "files": sorted_files
    }
