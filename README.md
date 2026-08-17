# RAG Chatbot

This project is a RAG (Retrieval-Augmented Generation) chatbot that allows users to upload their own PDF documents and ask questions about them. The chatbot retrieves relevant chunks from the documents and uses a local LLM to generate answers grounded in the provided context.

## Features

- PDF upload and ingestion from the UI
- Document chunking with metadata preservation
- Hybrid retrieval using ChromaDB (vector search) + BM25 (keyword search)
- Grounded answer generation from retrieved documents only
- Source citation showing which documents were used
- Simple Streamlit frontend for interactive Q&A

## Tech stack

| Layer | Technology |
| --- | --- |
| Language | Python 3.13 |
| Backend API | FastAPI 0.141.1 |
| Frontend UI | Streamlit 1.61.1 |
| LLM model | Ollama `llama3.2` (local, HTTP) |
| Embedding model | `all-MiniLM-L6-v2`, 384-dim (ChromaDB built-in ONNX) |
| Vector DB | ChromaDB 1.5.9 (persistent, on disk) |
| Chunking | LangChain `RecursiveCharacterTextSplitter` (800 chars, 120 overlap) |

## Project structure

```text
RAG_Chatbot/
├── app.sh                     # start/stop/restart/status for both services
├── README.md
├── .gitignore
├── backend/
│   ├── app.py                 # FastAPI app and endpoints
│   ├── start_backend.ps1      # PowerShell backend launcher
│   ├── requirements_2.txt     # current dependencies (use this one)
│   ├── requirements.txt       # legacy pins, superseded by requirements_2.txt
│   ├── __init__.py
│   ├── data/                  # uploaded PDFs
│   ├── chroma_db/             # persisted vector store
│   └── src/
│       ├── config.py          # all application settings
│       ├── ingest.py          # PDF extraction, chunking, indexing
│       ├── retrieval.py       # hybrid dense + BM25 retrieval
│       ├── llm_client.py      # Ollama HTTP client
│       └── __init__.py
├── frontend/
│   └── streamlit_app.py
└── logs/                      # runtime logs (not tracked)
```

## API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Service health check |
| POST | `/ingest` | Index PDFs from a server-side folder |
| POST | `/ingest-files` | Upload and index PDFs |
| POST | `/query` | Ask a question; returns `answer` and `sources` |

Interactive docs are served at `http://127.0.0.1:8000/docs`.

## Setup

1. Create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```bash
pip install -r backend/requirements_2.txt
```

3. Start Ollama and ensure a model is available, such as `llama3.2`:

```bash
ollama pull llama3.2
```

4. Start the FastAPI backend:

```bash
cd backend
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

5. Start the frontend:

```bash
cd frontend
streamlit run streamlit_app.py
```

6. Open `http://127.0.0.1:8501`, upload one or more PDFs in the sidebar, click
   "Ingest PDF docs", then ask questions in the chat box.

The first ingestion downloads the embedding model (~80 MB) to `~/.cache/chroma`
and can take a few minutes. Later runs reuse the cached model.

## Configuration

All settings live in [`backend/src/config.py`](backend/src/config.py) as plain
constants. The project holds no secrets, so there is no `.env` file — edit the
values directly and restart the backend.

| Setting | Default | Purpose |
| --- | --- | --- |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server address |
| `DEFAULT_MODEL` | `llama3.2` | Ollama model used for generation |
| `MAX_CONTEXT_CHUNKS` | `5` | Chunks retrieved per query |
| `COLLECTION_NAME` | `document_collection` | ChromaDB collection name |
| `DATA_DIR` | `backend/data` | Where uploaded PDFs are stored |
| `CHROMA_DIR` | `backend/chroma_db` | Where the vector store is persisted |

## Notes

- Upload documents via the browser UI or place them in `backend/data/`
- The chatbot only answers from the provided documents
- Sources show the filenames of the documents used to generate each answer
- Uploaded PDFs are re-indexed on every backend start; already-indexed chunks are skipped

### Suppressing telemetry warnings

Some dependencies (ChromaDB / OpenTelemetry) may emit non-critical telemetry warnings on startup. To suppress those locally without uninstalling packages, set the `OTEL_PYTHON_DISABLED` environment variable before starting the backend.

Temporary (PowerShell, current shell):

```powershell
$env:OTEL_PYTHON_DISABLED = "1"
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

Permanent for new shells (Windows):

```powershell
setx OTEL_PYTHON_DISABLED 1
```

Or use the included helper script to start the backend with telemetry disabled:

```powershell
cd backend
./start_backend.ps1
```

This script writes its PID to `backend/backend.pid` and logs to `./logs/`.

### Cross-platform control script (`app.sh`)

You can use the included `app.sh` to control both backend and frontend together. This is a POSIX shell script that works on macOS/Linux and in Windows environments with a POSIX shell (WSL or Git Bash).

Examples:

```bash
# start both services
./app.sh start

# stop both services
./app.sh stop

# restart both
./app.sh restart

# check status
./app.sh status
```

The script writes PID files to `./.pids/` and logs to `./logs/`.

## Example retrieval flow

1. PDFs are read and chunked
2. Chunks are embedded and stored in ChromaDB
3. BM25 is built from the same chunks
4. Query is answered by hybrid retrieval
5. The LLM is prompted with retrieved context only
