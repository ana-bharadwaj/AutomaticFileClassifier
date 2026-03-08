
import os
import time
import queue
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .sorter import is_temp_file, file_info

pending_queue: queue.Queue = queue.Queue(maxsize=0)

_stabilizing: set = set()
_stabilizing_lock = threading.Lock()


def wait_until_stable(filepath: str,
                      poll_interval: float = 0.5,
                      stable_threshold: int = 3) -> bool:
   
    if is_temp_file(filepath):
        return False

    last_size = -1
    stable_count = 0
    max_attempts = int(300 / poll_interval)

    for _ in range(max_attempts):
        try:
            current_size = os.path.getsize(filepath)
        except FileNotFoundError:
            return False

        if current_size == last_size and current_size > 0:
            stable_count += 1
            if stable_count >= stable_threshold:
                return True
        else:
            stable_count = 0

        last_size = current_size
        time.sleep(poll_interval)

    return False


def _stabilize_then_queue(filepath: str):
   
    try:
        if wait_until_stable(filepath):
            info = file_info(filepath)
            if info:
                pending_queue.put(info)
                print(f"[watcher] Queued: {os.path.basename(filepath)}")
    finally:
        with _stabilizing_lock:
            _stabilizing.discard(filepath)


class DownloadHandler(FileSystemEventHandler):
    

    def on_created(self, event):
        if event.is_directory:
            return

        filepath = event.src_path

        if is_temp_file(filepath):
            return

        with _stabilizing_lock:
            if filepath in _stabilizing:
                return
            _stabilizing.add(filepath)

        print(f"[watcher] Detected: {os.path.basename(filepath)}")

        t = threading.Thread(
            target=_stabilize_then_queue,
            args=(filepath,),
            daemon=True
        )
        t.start()

    def on_moved(self, event):
        if event.is_directory:
            return
        dest = event.dest_path
        if not is_temp_file(dest):
            fake_event = type('Event', (), {'src_path': dest, 'is_directory': False})()
            self.on_created(fake_event)


_observer: Observer = None
_watch_folder: str = None


def start_watcher(folder: str) -> bool:
 
    global _observer, _watch_folder

    if _observer and _observer.is_alive():
        stop_watcher()

    if not os.path.isdir(folder):
        print(f"[watcher] Not a directory: {folder}")
        return False

    _watch_folder = folder
    handler = DownloadHandler()
    _observer = Observer()
    _observer.schedule(handler, folder, recursive=False)
    _observer.start()
    print(f"[watcher] Watching: {folder}")
    return True


def stop_watcher():
    
    global _observer
    if _observer and _observer.is_alive():
        _observer.stop()
        _observer.join(timeout=5)
        print("[watcher] Stopped.")
    _observer = None


def is_watching() -> bool:
    return _observer is not None and _observer.is_alive()


def get_watch_folder() -> str:
    return _watch_folder


def drain_queue() -> list[dict]:

    items = []
    while True:
        try:
            items.append(pending_queue.get_nowait())
        except queue.Empty:
            break
    return items


def queue_size() -> int:
    return pending_queue.qsize()
