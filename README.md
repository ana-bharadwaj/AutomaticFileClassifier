# Downloads Sorter

Real-time file watcher that automatically sorts your downloads into
category/name-similarity folders, with per-file permission prompts.

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the app
python app.py

# 3. Open in browser
# http://localhost:5000
```

## How it works

```
app.py                  Flask server + shutdown hook
engine/
  permissions.py        File identity (path+size hash), grant/deny, state.json
  sorter.py             Extension grouping, name similarity (Union-Find), file moving
  watcher.py            Watchdog observer, download stabilization, thread-safe queue
  ollama.py             Optional AI fallback — filename metadata only, no content
templates/
  index.html            Single-page UI: setup → live feed → summary
```

## Folder structure produced

```
~/Sorted/
  Documents/
    tax_return/
      tax_return_2023.pdf
      tax_return_2024.pdf
    invoice/
      invoice_jan.pdf
      invoice_feb.pdf
  Images/
    vacation/
      vacation_day1.jpg
      vacation_day2.jpg
  Code/
    my_project/
      my_project_notes.py
```

## Ollama (optional)

For files that can't be categorized by extension or name similarity,
the app can ask a local Ollama model. Only the filename and size are sent.

```bash
# Install Ollama: https://ollama.com
ollama pull llama3.2
# Then restart the app — it detects Ollama automatically
```

## Security design

- Files are identified by path+size hash, never by reading content
- Permissions are persisted to ~/.downloads_sorter_state.json
- Every file requires explicit user approval before being moved
- Ollama fallback sends only: filename, extension, file size
- No file contents are ever read, stored, or transmitted
