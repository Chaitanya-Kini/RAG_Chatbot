# RAG Chatbot

This project is a RAG (Retrieval-Augmented Generation) chatbot that allows users to upload their own PDF documents and ask questions about them. The chatbot retrieves relevant chunks from the documents and uses a local LLM to generate answers grounded in the provided context.

Documents are organised into **projects**. Each project is an isolated knowledge
base: a chat answers from the selected project's documents only, and never from
any other project's. With no project selected, the chat falls back to general
chat and answers from the model's own knowledge instead.

## Features

- Two-page UI: **Chat** and **Projects**
- Projects as isolated knowledge bases, created from the UI
- General chat when no project is selected: answers come from the model alone
- Per-project PDF upload, with ingest and delete per document
- Document chunking with metadata preservation
- Hybrid retrieval using ChromaDB (vector search) + BM25 (keyword search), scoped to one project
- Grounded answer generation from retrieved documents only
- Source citation showing which documents were used

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
│   ├── data/                  # one folder per project, holding its PDFs
│   ├── chroma_db/             # persisted vector store
│   └── src/
│       ├── config.py          # all application settings
│       ├── projects.py        # project folders, name and filename validation
│       ├── ingest.py          # PDF extraction, chunking, indexing, deletion
│       ├── retrieval.py       # project-scoped hybrid dense + BM25 retrieval
│       ├── llm_client.py      # Ollama HTTP client
│       └── __init__.py
├── frontend/
│   ├── streamlit_app.py       # entry point: sidebar navigation
│   ├── api_client.py          # backend HTTP calls
│   ├── ui.py                  # shared CSS and presentational helpers
│   ├── .streamlit/config.toml # theme, headless start, telemetry opt-out
│   └── views/
│       ├── chat.py            # Chat page
│       └── projects.py        # Projects page
├── .pids/                     # PID files written by app.sh (not tracked)
└── logs/                      # runtime logs (not tracked)
```

## Projects

A project is a folder under `backend/data/`, and every chunk is stored with a
`project` field in its ChromaDB metadata:

```text
backend/data/
├── Project 1/          doc1.pdf  doc2.pdf  doc3.pdf
└── Project 2/          doc4.pdf  doc5.pdf
```

Selecting "Project 1" in the chat searches `doc1`–`doc3` and nothing else. The
scoping is enforced on both retrieval paths: the dense search passes
`where={"project": ...}` to ChromaDB, and BM25 indexes are built per project
rather than over the whole corpus, so one project's vocabulary cannot skew
another's term statistics.

The Projects page is laid out like a file explorer: a grid of project folders,
which open into the documents they contain.

Uploading and ingesting are separate steps. An uploaded PDF sits in the project
as "Not ingested" until you index it, either from a document's `⋯` menu or with
the "Ingest pending" button.

Project names are 1-64 characters, must start with a letter or digit, and accept
only letters, digits, spaces, hyphens and underscores. Upload filenames are
reduced to a bare `.pdf` leaf name, so neither can escape `backend/data/`.

## API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Service health check |
| GET | `/projects` | List projects with document and chunk counts |
| POST | `/projects` | Create a project (`{"name": ...}`) |
| DELETE | `/projects/{project}` | Delete a project, its PDFs and its chunks |
| GET | `/projects/{project}/documents` | List documents with index status |
| POST | `/projects/{project}/documents` | Upload PDFs into a project (no indexing) |
| POST | `/projects/{project}/ingest` | Index the project, or one `?filename=` |
| DELETE | `/projects/{project}/documents?filename=` | Delete a PDF and its chunks |
| POST | `/query` | Ask a question (`{"question": ..., "project": ...}`) |

`project` on `/query` is optional. Omit it (or send `null`) for **general chat**:
the question goes straight to the model with no retrieval and no document
context, and the response carries `grounded: false` with an empty `sources` list.
With a project, the response carries `grounded: true`.

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

6. Open `http://127.0.0.1:8501`. On the **Projects** page, create a project,
   upload PDFs into it and click "Ingest pending". Then switch to **Chat**, pick
   that project in the selector beside the message box and ask your questions.
   Leaving the selector on "General chat" asks the model directly instead.

The first ingestion downloads the embedding model (~80 MB) to `~/.cache/chroma`,
which occupies roughly 170 MB once unpacked, and can take a few minutes. Later
runs reuse the cached model.

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
| `DATA_DIR` | `backend/data` | Root folder holding the project folders |
| `CHROMA_DIR` | `backend/chroma_db` | Where the vector store is persisted |

## Notes

- Upload documents via the browser UI, or create a folder under `backend/data/`
  and put PDFs in it
- With a project selected, the chatbot answers only from that project's documents;
  with "General chat" selected it answers from the model's own knowledge and cites
  no sources
- Sources show the titles of the documents used to generate each answer
- Every project is re-indexed on backend start; already-indexed chunks are skipped
- A PDF placed directly in `backend/data/` rather than inside a project folder is
  ignored, since every query is project-scoped

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
2. Chunks are embedded and stored in ChromaDB, tagged with their project
3. On the first query for a project, a BM25 index is built from that project's
   chunks and cached until the collection changes
4. The query is answered by hybrid retrieval (dense + BM25, fused with
   Reciprocal Rank Fusion), filtered to the selected project
5. The LLM is prompted with the retrieved context only

General chat skips steps 3-5 entirely: the question goes straight to the model
with no context attached.
