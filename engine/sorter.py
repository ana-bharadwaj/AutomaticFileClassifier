import os
import re
import shutil
import difflib
from pathlib import Path
from collections import defaultdict

EXTENSION_MAP = {
    "Images":        {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
                      ".svg", ".tiff", ".ico", ".heic", ".raw", ".psd"},
    "Videos":        {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv",
                      ".webm", ".m4v", ".mpg", ".mpeg", ".3gp"},
    "Audio":         {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma",
                      ".m4a", ".opus", ".aiff"},
    "Documents":     {".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt",
                      ".md", ".tex", ".pages", ".epub"},
    "Spreadsheets":  {".xls", ".xlsx", ".csv", ".ods", ".numbers"},
    "Presentations": {".ppt", ".pptx", ".odp", ".key"},
    "Archives":      {".zip", ".tar", ".gz", ".rar", ".7z", ".bz2",
                      ".xz", ".dmg", ".iso", ".tar.gz"},
    "Code":          {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
                      ".java", ".c", ".cpp", ".h", ".go", ".rs", ".sh",
                      ".json", ".xml", ".yaml", ".yml", ".toml", ".sql",
                      ".rb", ".php", ".swift", ".kt"},
    "Executables":   {".exe", ".msi", ".app", ".deb", ".rpm", ".apk", ".pkg"},
    "Fonts":         {".ttf", ".otf", ".woff", ".woff2", ".eot"},
    "3D_Models":     {".obj", ".fbx", ".stl", ".blend", ".glb", ".gltf"},
    "Ebooks":        {".epub", ".mobi", ".azw", ".azw3"},
}

SIMILARITY_THRESHOLD = 0.65  \

TEMP_EXTENSIONS = {".crdownload", ".part", ".tmp", ".download", ".partial"}


def get_category(filepath: str) -> str:
   
    ext = Path(filepath).suffix.lower()
    for category, extensions in EXTENSION_MAP.items():
        if ext in extensions:
            return category
    return "Other"


def is_temp_file(filepath: str) -> bool:
    ext = Path(filepath).suffix.lower()
    name = Path(filepath).name.lower()
    return (
        ext in TEMP_EXTENSIONS or
        name.startswith(".") or
        name.endswith("~")
    )


def normalize_name(stem: str) -> str:
    s = stem.lower()
    s = re.sub(r"[\(\[\{][^\)\]\}]{0,20}[\)\]\}]", "", s)
    s = re.sub(r"\d{4}[-_/]\d{2}[-_/]\d{2}", "", s)
    s = re.sub(r"[-_]\d{4}$", "", s)
    s = re.sub(r"\bv?\d+(\.\d+){0,3}\b", "", s)
    s = re.sub(r"\b(final|draft|copy|backup|old|new|temp)\b", "", s)
    s = re.sub(r"[-_\s]+", " ", s).strip()
    return s


class UnionFind:
   

    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n  
    def find(self, x: int) -> int:
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, a: int, b: int):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return  
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1

    def groups(self) -> dict:
        result = defaultdict(list)
        for i in range(len(self.parent)):
            result[self.find(i)].append(i)
        return dict(result)


def cluster_by_name(files: list[dict]) -> dict[str, list[dict]]:
    
    if not files:
        return {}

    n = len(files)
    normalized = [normalize_name(f["stem"]) for f in files]
    uf = UnionFind(n)

    for i in range(n):
        for j in range(i + 1, n):
            if not normalized[i] or not normalized[j]:
                continue
            ratio = difflib.SequenceMatcher(
                None, normalized[i], normalized[j]
            ).ratio()
            if ratio >= SIMILARITY_THRESHOLD:
                uf.union(i, j)

    raw_groups = uf.groups()
    named_groups = {}

    for root, indices in raw_groups.items():
        members = [files[i] for i in indices]

        if len(members) == 1:
            label = members[0]["stem"]
        else:
            norm_names = [normalized[i] for i in indices]
            prefix = os.path.commonprefix(norm_names).strip("-_ ")
            label = prefix if len(prefix) >= 3 else norm_names[0]

        label = re.sub(r'[<>:"/\\|?*]', "", label).strip()
        label = label[:50]
        label = label or "Misc"

        named_groups[label] = members

    return named_groups


def build_sort_plan(files: list[dict]) -> dict[str, dict[str, list[dict]]]:
    
    by_category = defaultdict(list)
    for f in files:
        cat = get_category(f["path"])
        by_category[cat].append(f)

    plan = {}
    for category, cat_files in by_category.items():
        plan[category] = cluster_by_name(cat_files)

    return plan


def destination_path(dest_root: str, category: str, group: str, filename: str) -> str:
  
    folder = os.path.join(dest_root, category, group)
    target = os.path.join(folder, filename)

    if os.path.exists(target):
        stem = Path(filename).stem
        ext = Path(filename).suffix
        counter = 1
        while os.path.exists(target):
            target = os.path.join(folder, f"{stem} ({counter}){ext}")
            counter += 1

    return target


def move_file(src: str, dest: str) -> bool:

    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(src, dest)
        return True
    except (OSError, shutil.Error) as e:
        print(f"[sorter] Move failed: {src} → {dest}: {e}")
        return False


def file_info(filepath: str) -> dict:
   
    p = Path(filepath)
    try:
        stat = p.stat()
        return {
            "path": str(p),
            "name": p.name,
            "stem": p.stem,
            "ext": p.suffix.lower(),
            "size": stat.st_size,
            "size_human": human_size(stat.st_size),
            "category": get_category(str(p)),
            "is_temp": is_temp_file(str(p)),
        }
    except OSError:
        return {}


def human_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def scan_directory(directory: str) -> list[dict]:
 
    results = []
    try:
        for entry in Path(directory).iterdir():
            if entry.is_file():
                info = file_info(str(entry))
                if info and not info.get("is_temp"):
                    results.append(info)
    except PermissionError as e:
        print(f"[sorter] Permission denied scanning {directory}: {e}")
    return results
