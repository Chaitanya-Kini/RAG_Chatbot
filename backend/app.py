import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile

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
    from .src import projects as project_store
    from .src.config import DATA_DIR
    from .src.ingest import DocumentIndexer
    from .src.llm_client import OllamaClient
    from .src.retrieval import HybridRetriever
except ImportError:  # pragma: no cover
    from src import projects as project_store
    from src.config import DATA_DIR
    from src.ingest import DocumentIndexer
    from src.llm_client import OllamaClient
    from src.retrieval import HybridRetriever

logger = logging.getLogger("rag.app")

retriever = HybridRetriever()
indexer = DocumentIndexer()
llm_client = OllamaClient()


def _bootstrap() -> None:
    """Re-index every project on start, skipping chunks that are already stored."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    for name in project_store.list_projects():
        try:
            indexer.index_project(name)
        except Exception:
            # One unreadable PDF must not stop the other projects from loading.
            logger.exception("Failed to index project '%s'", name)

    retriever.refresh()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        _bootstrap()
    except Exception:
        # The API still starts, so /health and the Projects page stay reachable and
        # can report the problem instead of the server dying on boot.
        logger.exception("Startup indexing failed")
    yield


app = FastAPI(title="Document RAG Chatbot", version="0.2.0", lifespan=lifespan)


class QueryRequest(BaseModel):
    question: str
    # Omit the project to ask the model directly, with no document context.
    project: str | None = None


class QueryResponse(BaseModel):
    answer: str
    sources: list[str]
    project: str | None
    grounded: bool


class ProjectRequest(BaseModel):
    name: str


def _handle(error: project_store.ProjectError) -> HTTPException:
    status = 404 if isinstance(error, project_store.ProjectNotFound) else 400
    return HTTPException(status_code=status, detail=str(error))


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok", "message": "RAG Chatbot is running"}


@app.get("/projects")
def list_projects() -> dict:
    """Every project with its document and indexed-chunk counts."""
    payload = []
    for name in project_store.list_projects():
        counts = indexer.chunk_counts(name)
        documents = project_store.describe_documents(name)
        payload.append(
            {
                "name": name,
                "document_count": len(documents),
                "indexed_count": sum(1 for doc in documents if counts.get(doc["filename"])),
                "chunk_count": sum(counts.values()),
            }
        )
    return {"projects": payload}


@app.post("/projects", status_code=201)
def create_project(payload: ProjectRequest) -> dict:
    try:
        name = project_store.create_project(payload.name)
    except project_store.ProjectError as error:
        raise _handle(error) from error
    return {"status": "success", "project": name}


@app.delete("/projects/{project}")
def delete_project(project: str) -> dict:
    try:
        project_store.existing_project_dir(project)
        removed = indexer.delete_project(project)
        project_store.delete_project_files(project)
    except project_store.ProjectError as error:
        raise _handle(error) from error
    retriever.refresh()
    return {"status": "success", "project": project, "chunks_removed": removed}


@app.get("/projects/{project}/documents")
def list_documents(project: str) -> dict:
    try:
        documents = project_store.describe_documents(project)
    except project_store.ProjectError as error:
        raise _handle(error) from error

    counts = indexer.chunk_counts(project)
    for document in documents:
        chunks = counts.get(document["filename"], 0)
        document["chunks"] = chunks
        document["indexed"] = chunks > 0
    return {
        "project": project,
        "documents": documents,
        "chunk_count": sum(counts.values()),
    }


@app.post("/projects/{project}/documents")
async def upload_documents(project: str, files: list[UploadFile] = File(...)) -> dict:
    """Store PDFs in a project. Indexing is a separate, explicit step."""
    try:
        project_store.existing_project_dir(project)
    except project_store.ProjectError as error:
        raise _handle(error) from error

    saved: list[str] = []
    rejected: list[str] = []
    for file in files:
        content = await file.read()
        try:
            saved.append(project_store.save_upload(project, file.filename or "", content))
        except project_store.ProjectError:
            rejected.append(file.filename or "(unnamed)")

    if not saved:
        raise HTTPException(status_code=400, detail="No PDF files were uploaded.")
    return {
        "status": "success",
        "project": project,
        "files_uploaded": saved,
        "files_rejected": rejected,
    }


@app.post("/projects/{project}/ingest")
def ingest_project(project: str, filename: str | None = None) -> dict:
    """Index one document, or every document in the project when filename is omitted."""
    try:
        if filename:
            chunks = indexer.index_document(project, filename)
            documents = {filename: chunks}
        else:
            result = indexer.index_project(project)
            documents = result["documents"]
            chunks = result["chunks_indexed"]
    except project_store.ProjectError as error:
        raise _handle(error) from error

    retriever.refresh()
    return {
        "status": "success",
        "project": project,
        "chunks_indexed": chunks,
        "documents": documents,
    }


@app.delete("/projects/{project}/documents")
def delete_document(project: str, filename: str) -> dict:
    """Delete a PDF and its indexed chunks."""
    try:
        removed = indexer.delete_document(project, filename)
        project_store.delete_document_file(project, filename)
    except project_store.ProjectError as error:
        raise _handle(error) from error

    retriever.refresh()
    return {
        "status": "success",
        "project": project,
        "filename": filename,
        "chunks_removed": removed,
    }


@app.post("/query", response_model=QueryResponse)
def query_documents(payload: QueryRequest) -> QueryResponse:
    if not payload.project:
        # General chat: no project selected, so there is no context to ground in
        # and the "answer only from the documents" instruction does not apply.
        prompt = f"""You are a helpful assistant. Answer the user's question clearly and concisely.

Question: {payload.question}

Answer:
"""
        return QueryResponse(
            answer=llm_client.generate(prompt),
            sources=[],
            project=None,
            grounded=False,
        )

    try:
        project_store.existing_project_dir(payload.project)
    except project_store.ProjectError as error:
        raise _handle(error) from error

    # top_k is left to retrieve()'s default, which is MAX_CONTEXT_CHUNKS from config.
    results = retriever.retrieve(payload.question, payload.project)
    if not results:
        answer = "I don't have enough information in the provided documents to answer this question."
        sources: list[str] = []
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
        # Build a deduplicated ordered list of source titles
        raw_sources = [hit.get("metadata", {}).get("source", "Unknown") for hit in results]
        seen = set()
        sources = []
        for source in raw_sources:
            if source and source not in seen:
                seen.add(source)
                sources.append(source)

    return QueryResponse(
        answer=answer,
        sources=sources,
        project=payload.project,
        grounded=True,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
