import re
from typing import Any, Dict, List, Optional

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

    Prefer the indexer's (project, source, chunk_index) triple; fall back to the
    chunk text when metadata is missing. Keying on str(metadata) would be fragile,
    since it depends on dict ordering.
    """
    metadata = hit.get("metadata") or {}
    project = metadata.get("project")
    source = metadata.get("source")
    chunk_index = metadata.get("chunk_index")
    if source is not None and chunk_index is not None:
        return f"{project}#{source}#{chunk_index}"
    return hit["text"]


class _ProjectIndex:
    """One project's corpus plus its BM25 index."""

    def __init__(self, documents: List[str], metadatas: List[Dict[str, Any]]):
        self.documents = documents
        self.metadatas = metadatas
        self.bm25 = (
            BM25Okapi([re.findall(r"\w+", doc.lower()) for doc in documents])
            if documents
            else None
        )


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
        # BM25 is per project: scoring depends on corpus-wide term statistics, so a
        # single index built over every project would let one project's vocabulary
        # skew another's IDF values.
        self._indexes: Dict[str, _ProjectIndex] = {}
        # Chunk count the cached indexes were built from. None forces a rebuild.
        self._indexed_count: Optional[int] = None

    def refresh(self) -> None:
        """Drop the cached per-project indexes so the next query rebuilds them.

        Callers that mutate the collection (ingest, delete) must call this: the
        cheap count() check below cannot notice a delete and an add that happen to
        cancel out.
        """
        self._indexes = {}
        self._indexed_count = None

    # Kept for backwards compatibility with the pre-projects call sites.
    _load_index_state = refresh

    def _project_index(self, project: str) -> Optional[_ProjectIndex]:
        """Cached corpus for one project, rebuilt when the collection changes.

        Reading a corpus and building BM25 costs O(project), so doing it per query
        would make every request scale with the document count. collection.count()
        is a cheap COUNT query, which keeps the common path O(1).
        """
        if self.collection is None:
            return None

        total = self.collection.count()
        if self._indexed_count != total:
            self._indexes = {}
            self._indexed_count = total

        index = self._indexes.get(project)
        if index is None:
            data = self.collection.get(
                where={"project": project},
                include=["documents", "metadatas"],
            )
            index = _ProjectIndex(
                documents=data.get("documents") or [],
                metadatas=data.get("metadatas") or [],
            )
            self._indexes[project] = index
        return index

    def retrieve(
        self,
        query: str,
        project: str,
        top_k: int = MAX_CONTEXT_CHUNKS,
    ) -> List[Dict[str, Any]]:
        """Retrieve the best chunks for a query, restricted to one project."""
        if self.collection is None or not project:
            return []

        index = self._project_index(project)
        if index is None or not index.documents:
            return []

        dense_results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            # Scope the vector search to this project, so documents from other
            # projects can never enter the answer's context.
            where={"project": project},
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
            score = 1.0 - float(distance) / 2.0 if distance is not None else 0.0
            dense_hits.append({
                "text": document,
                "metadata": metadata or {},
                "score": score,
            })

        sparse_hits: List[Dict[str, Any]] = []
        if index.bm25 is not None:
            query_tokens = re.findall(r"\w+", query.lower())
            scores = index.bm25.get_scores(query_tokens)
            # Keep every candidate rather than dropping score <= 0. BM25 assigns
            # negative IDF to terms that appear in most documents, so on a small
            # corpus filtering by score would discard the entire sparse signal.
            for position, score in enumerate(scores):
                sparse_hits.append({
                    "text": index.documents[position],
                    "metadata": index.metadatas[position] if position < len(index.metadatas) else {},
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
    retriever.refresh()
    print("Retriever initialized")
