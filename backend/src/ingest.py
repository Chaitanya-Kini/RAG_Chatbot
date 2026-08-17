import re
from pathlib import Path
from typing import Any, Dict, List

import fitz
from langchain_text_splitters import RecursiveCharacterTextSplitter

try:
    from .config import CHROMA_DIR, COLLECTION_NAME, DATA_DIR
except ImportError:  # pragma: no cover
    from config import CHROMA_DIR, COLLECTION_NAME, DATA_DIR

try:
    import chromadb
    from chromadb.utils import embedding_functions
except ImportError:  # pragma: no cover
    chromadb = None
    embedding_functions = None


def extract_pdf_text(pdf_path: str | Path) -> str:
    doc = fitz.open(str(pdf_path))
    text_parts: List[str] = []
    for page in doc:
        page_text = page.get_text("text")
        if page_text.strip():
            text_parts.append(page_text)
    doc.close()
    return "\n\n".join(text_parts)


def sanitize_document_name(path: Path) -> str:
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
        self.documents: List[str] = []
        self.metadatas: List[Dict[str, Any]] = []

    def _build_chunks(self, raw_text: str, source_name: str) -> List[Dict[str, Any]]:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=120,
            separators=["\n\n", "\n", ". ", " "],
        )
        chunk_texts = splitter.split_text(raw_text)

        chunks: List[Dict[str, Any]] = []
        for index, chunk in enumerate(chunk_texts):
            cleaned = re.sub(r"\s+", " ", chunk).strip()
            if not cleaned:
                continue
            chunks.append(
                {
                    "id": f"{source_name}-{index}",
                    "text": cleaned,
                    "metadata": {
                        "source": source_name,
                        "document_name": source_name,
                        "chunk_index": index,
                    },
                }
            )
        return chunks

    def index_folder(self, folder: str | Path) -> int:
        if self.collection is None:
            raise RuntimeError("ChromaDB is not available. Install backend requirements first.")

        folder = Path(folder)
        pdf_files = sorted(folder.glob("*.pdf"))
        if not pdf_files:
            return 0

        all_chunks: List[Dict[str, Any]] = []
        for pdf_file in pdf_files:
            text = extract_pdf_text(pdf_file)
            if not text.strip():
                continue
            source_name = sanitize_document_name(pdf_file)
            all_chunks.extend(self._build_chunks(text, source_name))

        if not all_chunks:
            return 0

        texts = [chunk["text"] for chunk in all_chunks]
        ids = [chunk["id"] for chunk in all_chunks]
        metadatas = [chunk["metadata"] for chunk in all_chunks]

        # Check for already-existing ids in the collection and skip them to avoid duplicate adds.
        # Note: ids are always returned by get(); passing them via include= is rejected by Chroma.
        try:
            existing_state = self.collection.get(include=[]) or {}
            existing_ids = set(existing_state.get("ids") or [])
        except Exception:
            existing_ids = set()

        new_texts = []
        new_ids = []
        new_metadatas = []
        for chunk in all_chunks:
            cid = chunk["id"]
            if cid in existing_ids:
                continue
            new_ids.append(cid)
            new_texts.append(chunk["text"])
            new_metadatas.append(chunk["metadata"])

        if not new_ids:
            # Nothing new to add
            self.documents = [c["text"] for c in all_chunks]
            self.metadatas = [c["metadata"] for c in all_chunks]
            return 0

        # No explicit embeddings= : Chroma embeds the documents with the collection's
        # embedding function, which is the same one used for queries.
        self.collection.add(
            ids=new_ids,
            documents=new_texts,
            metadatas=new_metadatas,
        )

        # Update cached lists (note: this caches only the most recently indexed batch)
        self.documents = new_texts
        self.metadatas = new_metadatas
        return len(new_ids)

    def count(self) -> int:
        if self.collection is None:
            return 0
        return self.collection.count()


if __name__ == "__main__":
    indexer = DocumentIndexer()
    indexer.index_folder(DATA_DIR)
    print(f"Indexed {indexer.count()} chunks")
