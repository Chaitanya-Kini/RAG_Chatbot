from pathlib import Path

import logging

from fastapi import FastAPI, File, UploadFile

# Reduce noisy telemetry/otel/chromadb logs that surface harmless instrumentation
for logger_name in (
    "chromadb",
    "opentelemetry",
    "opentelemetry.instrumentation",
    "opentelemetry.exporter",
):
    logging.getLogger(logger_name).setLevel(logging.ERROR)
from pydantic import BaseModel

try:
    from .src.ingest import DocumentIndexer
    from .src.llm_client import OllamaClient
    from .src.retrieval import HybridRetriever
except ImportError:  # pragma: no cover
    from src.ingest import DocumentIndexer
    from src.llm_client import OllamaClient
    from src.retrieval import HybridRetriever

app = FastAPI(title="Document RAG Chatbot", version="0.1.0")

retriever = HybridRetriever()
indexer = DocumentIndexer()
llm_client = OllamaClient()


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    answer: str
    sources: list[str]


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok", "message": "3GPP RAG Chatbot is running"}


@app.post("/ingest")
def ingest_documents(folder: str | None = None) -> dict:
    target_folder = Path(folder) if folder else Path(__file__).resolve().parent / "data"
    count = indexer.index_folder(target_folder)
    retriever._load_index_state()
    return {"status": "success", "chunks_indexed": count}


@app.post("/ingest-files")
async def ingest_uploaded_files(files: list[UploadFile] = File(...)) -> dict:
    target_folder = Path(__file__).resolve().parent / "data"
    target_folder.mkdir(parents=True, exist_ok=True)

    saved_files: list[str] = []
    for file in files:
        if not file.filename:
            continue
        if not file.filename.lower().endswith(".pdf"):
            continue
        destination = target_folder / file.filename
        content = await file.read()
        destination.write_bytes(content)
        saved_files.append(file.filename)

    if not saved_files:
        return {"status": "error", "message": "No PDF files were uploaded."}

    count = indexer.index_folder(target_folder)
    retriever._load_index_state()
    return {
        "status": "success",
        "files_uploaded": saved_files,
        "documents_indexed": count,
    }


@app.post("/query", response_model=QueryResponse)
def query_documents(payload: QueryRequest) -> QueryResponse:
    results = retriever.retrieve(payload.question, top_k=5)
    if not results:
        answer = "I don't have enough information in the provided documents to answer this question."
        sources = []
    else:
        context = "\n\n".join(
            f"[{idx + 1}] {hit['text']}\nSource: {hit.get('metadata', {}).get('source', 'Unknown')}"
            for idx, hit in enumerate(results)
        )
        prompt = f"""You are a helpful assistant. Answer questions using only the provided context.
Do not use outside knowledge or make assumptions.
If the context does not contain enough information to answer, respond exactly:
Information not found in the provided documents.

Context:
{context}

Question: {payload.question}

Answer:
"""
        answer = llm_client.generate(prompt)
        # Build a deduplicated ordered list of source filenames
        raw_sources = [hit.get("metadata", {}).get("source", "Unknown") for hit in results]
        seen = set()
        sources = []
        for s in raw_sources:
            if s and s not in seen:
                seen.add(s)
                sources.append(s)

    return QueryResponse(answer=answer, sources=sources)


@app.on_event("startup")
def startup_event() -> None:
    data_folder = Path(__file__).resolve().parent / "data"
    try:
        indexer.index_folder(data_folder)
        retriever._load_index_state()
    except Exception:
        pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
