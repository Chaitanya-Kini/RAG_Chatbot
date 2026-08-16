import re
from typing import Any, Dict, List

from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

try:
    from .config import CHROMA_DIR, COLLECTION_NAME, EMBEDDING_MODEL, MAX_CONTEXT_CHUNKS
except ImportError:  # pragma: no cover
    from config import CHROMA_DIR, COLLECTION_NAME, EMBEDDING_MODEL, MAX_CONTEXT_CHUNKS

try:
    import chromadb
except ImportError:  # pragma: no cover
    chromadb = None


class HybridRetriever:
    def __init__(self):
        self.embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        self.client = chromadb.PersistentClient(path=str(CHROMA_DIR)) if chromadb else None
        self.collection = (
            self.client.get_or_create_collection(name=COLLECTION_NAME)
            if self.client is not None
            else None
        )
        self.documents: List[str] = []
        self.metadatas: List[Dict[str, Any]] = []
        self.bm25 = None

    def _load_index_state(self) -> None:
        if self.collection is None:
            return
        collection_data = self.collection.get(include=["documents", "metadatas"])
        self.documents = collection_data.get("documents", [])
        self.metadatas = collection_data.get("metadatas", [])
        if not self.documents:
            self.bm25 = None
            return
        tokenized_docs = [re.findall(r"\w+", doc.lower()) for doc in self.documents]
        self.bm25 = BM25Okapi(tokenized_docs)

    def retrieve(self, query: str, top_k: int = MAX_CONTEXT_CHUNKS) -> List[Dict[str, Any]]:
        if self.collection is None:
            return []

        self._load_index_state()
        if not self.documents:
            return []

        dense_results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        dense_hits: List[Dict[str, Any]] = []
        fetched_documents = dense_results.get("documents", [[]])[0]
        fetched_metadatas = dense_results.get("metadatas", [[]])[0]
        fetched_distances = dense_results.get("distances", [[]])[0]
        for document, metadata, distance in zip(fetched_documents, fetched_metadatas, fetched_distances):
            score = max(0.0, 1.0 - float(distance)) if distance is not None else 0.5
            dense_hits.append({
                "text": document,
                "metadata": metadata or {},
                "score": score,
            })

        sparse_hits: List[Dict[str, Any]] = []
        if self.bm25 is not None:
            query_tokens = re.findall(r"\w+", query.lower())
            scores = self.bm25.get_scores(query_tokens)
            for index, score in enumerate(scores):
                if score <= 0:
                    continue
                sparse_hits.append({
                    "text": self.documents[index],
                    "metadata": self.metadatas[index] if index < len(self.metadatas) else {},
                    "score": float(score),
                })

        combined: Dict[str, Dict[str, Any]] = {}
        for hit in dense_hits:
            key = hit["text"] + str(hit.get("metadata", {}))
            combined[key] = {**hit, "score": hit["score"]}

        for hit in sparse_hits:
            key = hit["text"] + str(hit.get("metadata", {}))
            if key in combined:
                combined[key]["score"] += hit["score"] * 0.5
            else:
                combined[key] = {**hit, "score": hit["score"] * 0.6}

        ranked_hits = sorted(combined.values(), key=lambda item: item["score"], reverse=True)

        # Deduplicate hits by source filename while preserving score ordering
        seen_sources = set()
        deduped_hits = []
        for hit in ranked_hits:
            src = hit.get("metadata", {}).get("source")
            if not src:
                # if no source metadata, include once under 'Unknown'
                src = "Unknown"
            if src in seen_sources:
                continue
            seen_sources.add(src)
            deduped_hits.append(hit)

        return deduped_hits[:top_k]

    def answer(self, question: str, top_k: int = MAX_CONTEXT_CHUNKS) -> Dict[str, Any]:
        hits = self.retrieve(question, top_k=top_k)
        if not hits:
            return {
                "answer": "Information not found in 3GPP documentation.",
                "sources": [],
                "context": [],
            }

        context = "\n\n".join(
            f"[{idx + 1}] {hit['text']}\nSource: {hit.get('metadata', {}).get('source', 'Unknown')}"
            for idx, hit in enumerate(hits)
        )

        prompt = f"""You are a telecom specification assistant.
Your job is to answer only from the provided 3GPP context.
Do not use outside knowledge. If the answer is not supported by the context, reply exactly:
Information not found in 3GPP documentation.

Provide explicit source references using the document name and section if available.

Context:
{context}

Question: {question}

Answer:
"""
        return {
            "answer": prompt,
            "sources": [hit.get("metadata", {}).get("source", "Unknown") for hit in hits],
            "context": [hit["text"] for hit in hits],
        }


if __name__ == "__main__":
    retriever = HybridRetriever()
    retriever._load_index_state()
    print("Retriever initialized")
