import os
import atexit
from flask import Flask, jsonify, request, render_template

from engine.permissions import (
    load_state, save_state,
    grant_permission, deny_permission,
    grant_all, deny_all,
    has_permission, is_denied,
    log_sorted_file, get_session_summary
)
from engine.sorter import (
    scan_directory, file_info,
    build_sort_plan, destination_path, move_file,
    get_category
)
from engine.watcher import (
    start_watcher, stop_watcher,
    is_watching, get_watch_folder,
    drain_queue
)
from engine.ollama import is_ollama_available, suggest_folder

app = Flask(__name__)

app_state = {
    "watch_folder": None,
    "dest_folder": None,
    "db": load_state(),
    "existing_scanned": False,
}


@app.route("/api/resolve-path", methods=["POST"])
def resolve_path():
   
    data = request.json
    folder_name = data.get("folder_name", "").strip()
    hints = data.get("hints", [])
   
    relative_path = data.get("relative_path", "").strip()

    if not folder_name:
        return jsonify({"path": None})

    home = os.path.expanduser("~")

    search_roots = [
        home,
        os.path.join(home, "Downloads"),
        os.path.join(home, "Desktop"),
        os.path.join(home, "Documents"),
        os.path.join(home, "Pictures"),
        os.path.join(home, "Videos"),
        os.path.join(home, "Music"),
    ]

    search_roots += ["/tmp", "/Users", "/home"]

    import string
    for drive in string.ascii_uppercase:
        drive_path = f"{drive}:\\"
        if os.path.isdir(drive_path):
            search_roots.append(drive_path)
            users_dir = os.path.join(drive_path, "Users")
            if os.path.isdir(users_dir):
                try:
                    for user in os.listdir(users_dir):
                        user_home = os.path.join(users_dir, user)
                        if os.path.isdir(user_home):
                            search_roots.append(user_home)
                            for sub in ["Downloads", "Desktop", "Documents", "Pictures", "Videos", "Music"]:
                                search_roots.append(os.path.join(user_home, sub))
                except OSError:
                    pass

    candidates = []

    for root in search_roots:
        if not os.path.isdir(root):
            continue
        if os.path.basename(root) == folder_name and os.path.isdir(root):
            candidates.append(root)
        candidate = os.path.join(root, folder_name)
        if os.path.isdir(candidate):
            candidates.append(candidate)

    seen = set()
    unique = []
    for c in candidates:
        norm = os.path.normpath(c)
        if norm not in seen:
            seen.add(norm)
            unique.append(c)
    candidates = unique

    if not candidates:
        return jsonify({"path": None})

    def hint_score(path):
        try:
            contents = set(os.listdir(path))
            return sum(1 for h in hints if h in contents)
        except OSError:
            return 0

    if len(candidates) == 1 or not hints:
        return jsonify({"path": os.path.normpath(candidates[0])})

    best = max(candidates, key=hint_score)
    return jsonify({"path": os.path.normpath(best)})



@app.route("/api/setup", methods=["POST"])
def setup():
    
    data = request.json
    watch = data.get("watch_folder", "").strip()
    dest = data.get("dest_folder", "").strip()

    for ch in ('"', "'"):
        if watch.startswith(ch) and watch.endswith(ch):
            watch = watch[1:-1]
        if dest.startswith(ch) and dest.endswith(ch):
            dest = dest[1:-1]

    watch = os.path.normpath(os.path.expanduser(watch.strip()))
    dest  = os.path.normpath(os.path.expanduser(dest.strip()))

    if not os.path.isdir(watch):
        return jsonify({"error": f"Watch folder does not exist: {watch}"}), 400

    try:
        os.makedirs(dest, exist_ok=True)
    except OSError as e:
        return jsonify({"error": f"Cannot create destination: {e}"}), 400

    app_state["watch_folder"] = watch
    app_state["dest_folder"] = dest
    app_state["existing_scanned"] = False

    ok = start_watcher(watch)
    if not ok:
        return jsonify({"error": "Failed to start watcher"}), 500

    return jsonify({
        "ok": True,
        "watch_folder": watch,
        "dest_folder": dest,
        "message": f"Watching {watch} → sorting into {dest}"
    })


@app.route("/api/status", methods=["GET"])
def status():
    return jsonify({
        "watching": is_watching(),
        "watch_folder": app_state["watch_folder"],
        "dest_folder": app_state["dest_folder"],
        "ollama_available": is_ollama_available(),
        "existing_scanned": app_state["existing_scanned"],
        "sorted_count": len(app_state["db"].get("sorted_files", [])),
    })


@app.route("/api/scan-existing", methods=["GET"])
def scan_existing():
    watch = app_state.get("watch_folder")
    if not watch:
        return jsonify({"error": "No watch folder set"}), 400

    files = scan_directory(watch)
    plan = build_sort_plan(files)
    dest = app_state["dest_folder"]
    preview = []
    for category, groups in plan.items():
        for group, members in groups.items():
            for f in members:
                dest_p = destination_path(dest, category, group, f["name"]) if dest else None
                preview.append({
                    **f,
                    "category": category,
                    "group": group,
                    "dest_preview": dest_p,
                })

    app_state["existing_scanned"] = True
    return jsonify({
        "files": preview,
        "total": len(preview),
        "categories": list(plan.keys()),
    })


@app.route("/api/permission", methods=["POST"])
def set_permission():
    data = request.json
    filepath = data.get("path", "")
    action = data.get("action", "")

    if not filepath or not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404

    if action == "grant":
        grant_permission(filepath, app_state["db"])
        result = _sort_file(filepath)
        return jsonify({"ok": True, "sorted": result})
    elif action == "deny":
        deny_permission(filepath, app_state["db"])
        return jsonify({"ok": True, "sorted": None})
    else:
        return jsonify({"error": "action must be 'grant' or 'deny'"}), 400


@app.route("/api/bulk-permission", methods=["POST"])
def bulk_permission():
    data = request.json
    paths = data.get("paths", [])
    action = data.get("action", "grant")

    results = []
    for path in paths:
        if not os.path.exists(path):
            continue
        if action == "grant":
            grant_permission(path, app_state["db"])
            result = _sort_file(path)
            results.append({"path": path, "sorted": result})
        else:
            deny_permission(path, app_state["db"])
            results.append({"path": path, "sorted": None})

    return jsonify({"ok": True, "results": results, "count": len(results)})


@app.route("/api/pending", methods=["GET"])
def get_pending():
    files = drain_queue()
    undecided = [
        f for f in files
        if not has_permission(f["path"], app_state["db"])
        and not is_denied(f["path"], app_state["db"])
        and os.path.exists(f["path"])
    ]
    return jsonify({"files": undecided})


@app.route("/api/summary", methods=["GET"])
def summary():
    return jsonify(get_session_summary(app_state["db"]))


@app.route("/api/stop", methods=["POST"])
def stop():
    stop_watcher()
    summary_data = get_session_summary(app_state["db"])
    app_state["watch_folder"] = None
    return jsonify({
        "ok": True,
        "summary": summary_data,
        "message": f"Sorted {summary_data['total']} files."
    })


@app.route("/")
def index():
    return render_template("index.html")


def _sort_file(filepath: str) -> dict | None:
    
    dest_root = app_state.get("dest_folder")
    if not dest_root or not os.path.exists(filepath):
        return None

    info = file_info(filepath)
    if not info:
        return None

    category = info["category"]
    group = info["stem"]


    existing_in_cat = _get_existing_groups(dest_root, category)

    if category == "Other" and is_ollama_available():
        ai_suggestion = suggest_folder(
            filename=info["name"],
            ext=info["ext"],
            size_bytes=info["size"],
            existing_folders=existing_in_cat
        )
        if ai_suggestion:
            group = ai_suggestion
    elif existing_in_cat:
        import difflib
        from engine.sorter import normalize_name
        norm = normalize_name(info["stem"])
        best_ratio = 0
        best_group = group
        for eg in existing_in_cat:
            ratio = difflib.SequenceMatcher(None, norm, normalize_name(eg)).ratio()
            if ratio > best_ratio and ratio >= 0.60:
                best_ratio = ratio
                best_group = eg
        group = best_group

    dest = destination_path(dest_root, category, group, info["name"])
    success = move_file(filepath, dest)

    if success:
        log_sorted_file(
            src=filepath,
            dest=dest,
            category=category,
            group=group,
            state=app_state["db"]
        )
        return {"src": filepath, "dest": dest, "category": category, "group": group}

    return None


def _get_existing_groups(dest_root: str, category: str) -> list[str]:
    cat_path = os.path.join(dest_root, category)
    if not os.path.isdir(cat_path):
        return []
    return [d for d in os.listdir(cat_path) if os.path.isdir(os.path.join(cat_path, d))]


def _on_shutdown():
    print("\n[app] Shutting down...")
    stop_watcher()
    summary = get_session_summary(app_state["db"])
    print(f"[app] Session complete. Sorted {summary['total']} files.")
    if summary["by_category"]:
        for cat, count in summary["by_category"].items():
            print(f"  {cat}: {count} file(s)")
    print(f"[app] All files in: {app_state.get('dest_folder', 'N/A')}")


atexit.register(_on_shutdown)


if __name__ == "__main__":
    print("Downloads Sorter starting...")
    print("Open http://localhost:5000 in your browser")
   
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)