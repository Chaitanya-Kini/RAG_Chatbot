import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pymupdf
from langchain_text_splitters import RecursiveCharacterTextSplitter

try:
    from . import projects as project_store
    from .config import CHROMA_DIR, COLLECTION_NAME
except ImportError:  # pragma: no cover
    import projects as project_store
    from config import CHROMA_DIR, COLLECTION_NAME

try:
    import chromadb
    from chromadb.utils import embedding_functions
except ImportError:  # pragma: no cover
    chromadb = None
    embedding_functions = None

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120

# Chunk ids embed the project and filename so the same PDF can live in two
# projects without one overwriting the other's chunks.
ID_SEPARATOR = "::"


def extract_pdf_text(pdf_path: str | Path) -> str:
    doc = pymupdf.open(str(pdf_path))
    text_parts: List[str] = []
    for page in doc:
        page_text = page.get_text("text")
        if page_text.strip():
            text_parts.append(page_text)
    doc.close()
    return "\n\n".join(text_parts)


def sanitize_document_name(path: Path) -> str:
    """Human-readable document title, used for answer citations."""
    return path.stem.replace("_", " ").strip()


class DocumentIndexer:
    def __init__(self):
        # ONNX MiniLM-L6-v2, the same embedder the retriever uses. Chroma embeds
        # documents on add() and queries on query(), so both sides stay compatible.
        self.embedding_function = (
            embedding_functions.DefaultEmbeddingFunction() if embedding_functions else None
        )
        self.client = chromadb.PersistentClient(path=str(CHROMA_DIR)) if chromadb else None
        self.collection = (
            self.client.get_or_create_collection(
                name=COLLECTION_NAME,
                embedding_function=self.embedding_function,
            )
            if self.client is not None
            else None
        )

    def _require_collection(self):
        if self.collection is None:
            raise RuntimeError("ChromaDB is not available. Install backend requirements first.")
        return self.collection

    def _build_chunks(self, raw_text: str, project: str, path: Path) -> List[Dict[str, Any]]:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " "],
        )
        chunk_texts = splitter.split_text(raw_text)
        title = sanitize_document_name(path)

        chunks: List[Dict[str, Any]] = []
        for index, chunk in enumerate(chunk_texts):
            cleaned = re.sub(r"\s+", " ", chunk).strip()
            if not cleaned:
                continue
            chunks.append(
                {
                    "id": ID_SEPARATOR.join((project, path.name, str(index))),
                    "text": cleaned,
                    "metadata": {
                        # "project" and "filename" drive retrieval filtering and
                        # deletion; "source" is the title shown to the user.
                        "project": project,
                        "filename": path.name,
                        "source": title,
                        "document_name": title,
                        "chunk_index": index,
                    },
                }
            )
        return chunks

    def _chunk_ids(self, project: str, filename: Optional[str] = None) -> List[str]:
        """Ids of the stored chunks for a project, or for one document in it."""
        collection = self._require_collection()
        if filename is None:
            where: Dict[str, Any] = {"project": project}
        else:
            # Chroma requires an explicit $and once a filter has two fields.
            where = {"$and": [{"project": project}, {"filename": filename}]}
        # ids are always returned by get(); passing them via include= is rejected.
        state = collection.get(where=where, include=[]) or {}
        return list(state.get("ids") or [])

    def index_document(self, project: str, filename: str) -> int:
        """Index one PDF. Returns the number of newly added chunks."""
        collection = self._require_collection()
        path = project_store.document_path(project, filename)
        if not path.is_file():
            raise project_store.ProjectNotFound(
                f"'{path.name}' does not exist in project '{project}'."
            )

        text = extract_pdf_text(path)
        if not text.strip():
            return 0

        chunks = self._build_chunks(text, project, path)
        if not chunks:
            return 0

        existing = set(self._chunk_ids(project, path.name))
        new_chunks = [chunk for chunk in chunks if chunk["id"] not in existing]
        if not new_chunks:
            return 0

        # No explicit embeddings= : Chroma embeds the documents with the collection's
        # embedding function, which is the same one used for queries.
        collection.add(
            ids=[chunk["id"] for chunk in new_chunks],
            documents=[chunk["text"] for chunk in new_chunks],
            metadatas=[chunk["metadata"] for chunk in new_chunks],
        )
        return len(new_chunks)

    def index_project(self, project: str) -> Dict[str, Any]:
        """Index every PDF in a project, skipping chunks that are already stored."""
        self._require_collection()
        indexed: Dict[str, int] = {}
        for path in project_store.list_documents(project):
            indexed[path.name] = self.index_document(project, path.name)
        return {
            "project": project,
            "documents": indexed,
            "chunks_indexed": sum(indexed.values()),
        }

    def delete_document(self, project: str, filename: str) -> int:
        """Remove a document's chunks from the vector store."""
        collection = self._require_collection()
        ids = self._chunk_ids(project, filename)
        if ids:
            collection.delete(ids=ids)
        return len(ids)

    def delete_project(self, project: str) -> int:
        collection = self._require_collection()
        ids = self._chunk_ids(project)
        if ids:
            collection.delete(ids=ids)
        return len(ids)

    def chunk_counts(self, project: str) -> Dict[str, int]:
        """Stored chunk count per filename, for the project's index status."""
        collection = self._require_collection()
        state = collection.get(where={"project": project}, include=["metadatas"]) or {}
        counts: Dict[str, int] = {}
        for metadata in state.get("metadatas") or []:
            filename = (metadata or {}).get("filename")
            if filename:
                counts[filename] = counts.get(filename, 0) + 1
        return counts

    def count(self) -> int:
        if self.collection is None:
            return 0
        return self.collection.count()


if __name__ == "__main__":
    indexer = DocumentIndexer()
    for name in project_store.list_projects():
        result = indexer.index_project(name)
        print(f"{name}: +{result['chunks_indexed']} chunks")
    print(f"Total stored chunks: {indexer.count()}")
