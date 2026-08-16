# RAG Chatbot

This project is a RAG (Retrieval-Augmented Generation) chatbot that allows users to upload their own PDF documents and ask questions about them. The chatbot retrieves relevant chunks from the documents and uses a local LLM to generate answers grounded in the provided context.

## Features

- PDF upload and ingestion from the UI
- Document chunking with metadata preservation
- Hybrid retrieval using ChromaDB (vector search) + BM25 (keyword search)
- Reranking for improved precision
- Grounded answer generation from retrieved documents only
- Source citation showing which documents were used
- Optional evaluation metrics (groundedness, relevance)
- Simple Streamlit frontend for interactive Q&A

## Project structure

```text
RAG_Chatbot/
├── backend/
│   ├── app.py
│   ├── requirements.txt
│   ├── data/
│   ├── chroma_db/
│   └── src/
│       ├── config.py
│       ├── ingest.py
│       ├── retrieval.py
│       ├── llm_client.py
│       └── eval.py
├── frontend/
│   └── streamlit_app.py
├── .gitignore
└── README.md
```

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

2. Install backend dependencies:

```bash
pip install -r backend/requirements.txt
```

3. Start Ollama and ensure a model is available, such as `llama3.2`.

```bash
ollama pull llama3.2
```

4. Upload one or more PDF documents through the Streamlit UI, or place them in `backend/data/` and click "Ingest PDF docs".

5. Start the FastAPI backend:

```bash
cd backend
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

6. Start the frontend:

```bash
cd frontend
streamlit run streamlit_app.py
```

7. Upload your PDF documents and ask questions in the UI.

## Notes

- Upload documents via the browser UI or place them in `backend/data/`
- The chatbot only answers from the provided documents
- Sources show the filenames of the documents used to generate each answer

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
6. The output is checked for groundedness and relevance
