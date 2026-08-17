import re
from typing import Any, Dict, List

from rank_bm25 import BM25Okapi

try:
    from .config import CHROMA_DIR, COLLECTION_NAME, MAX_CONTEXT_CHUNKS
except ImportError:  # pragma: no cover
    from config import CHROMA_DIR, COLLECTION_NAME, MAX_CONTEXT_CHUNKS

try:
    import chromadb
    from chromadb.utils import embedding_functions
except ImportError:  # pragma: no cover
    chromadb = None
    embedding_functions = None

# Reciprocal Rank Fusion constant. 60 is the value from the original RRF paper and
# the usual default; larger values flatten the contribution of top ranks.
RRF_K = 60

# How many BM25 candidates to feed into fusion, as a multiple of top_k.
SPARSE_CANDIDATE_FACTOR = 4


def _hit_key(hit: Dict[str, Any]) -> str:
    """Stable identity for a chunk, used to merge dense and sparse hits.

    Prefer the indexer's (source, chunk_index) pair; fall back to the chunk text
    when metadata is missing. Keying on str(metadata) would be fragile, since it
    depends on dict ordering.
    """
    metadata = hit.get("metadata") or {}
    source = metadata.get("source")
    chunk_index = metadata.get("chunk_index")
    if source is not None and chunk_index is not None:
        return f"{source}#{chunk_index}"
    return hit["text"]


class HybridRetriever:
    def __init__(self):
        # Must match the indexer's embedding function, or query vectors and
        # document vectors would not live in the same space.
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
            # Chroma's default space is squared L2. The embedding function returns
            # unit-normalised vectors, so squared L2 and cosine relate exactly as
            # d = 2 * (1 - cos), giving cos = 1 - d / 2 over the range [-1, 1].
            # The previous "1 - d" assumed cosine distance and clamped most hits to 0.
            score = 1.0 - float(distance) / 2.0 if distance is not None else 0.0
            dense_hits.append({
                "text": document,
                "metadata": metadata or {},
                "score": score,
            })

        sparse_hits: List[Dict[str, Any]] = []
        if self.bm25 is not None:
            query_tokens = re.findall(r"\w+", query.lower())
            scores = self.bm25.get_scores(query_tokens)
            # Keep every candidate rather than dropping score <= 0. BM25 assigns
            # negative IDF to terms that appear in most documents, so on a small
            # corpus filtering by score would discard the entire sparse signal.
            for index, score in enumerate(scores):
                sparse_hits.append({
                    "text": self.documents[index],
                    "metadata": self.metadatas[index] if index < len(self.metadatas) else {},
                    "score": float(score),
                })
            sparse_hits.sort(key=lambda item: item["score"], reverse=True)
            del sparse_hits[top_k * SPARSE_CANDIDATE_FACTOR :]

        # Reciprocal Rank Fusion. Dense similarity is bounded to [-1, 1] while BM25
        # is unbounded, so summing the raw scores let BM25 dominate. Fusing on rank
        # instead makes the two signals comparable without any tuning weights.
        combined: Dict[str, Dict[str, Any]] = {}
        for hits in (dense_hits, sparse_hits):
            ranked = sorted(hits, key=lambda item: item["score"], reverse=True)
            for rank, hit in enumerate(ranked):
                key = _hit_key(hit)
                entry = combined.get(key)
                if entry is None:
                    entry = {
                        "text": hit["text"],
                        "metadata": hit.get("metadata") or {},
                        "score": 0.0,
                    }
                    combined[key] = entry
                entry["score"] += 1.0 / (RRF_K + rank + 1)

        ranked_hits = sorted(combined.values(), key=lambda item: item["score"], reverse=True)

        # Return the best chunks by relevance. Chunks are deliberately not deduplicated
        # by source: several passages from one document are often needed to answer a
        # question. The response's source list is deduplicated separately in app.py.
        return ranked_hits[:top_k]


if __name__ == "__main__":
    retriever = HybridRetriever()
    retriever._load_index_state()
    print("Retriever initialized")
