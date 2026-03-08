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
