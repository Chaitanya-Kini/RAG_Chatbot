"""Application settings.

These are plain constants. The project holds no secrets, so settings live in
source rather than in a .env file -- edit the values below to change behaviour.
"""

from pathlib import Path

# backend/ directory, used to anchor the storage paths below
BASE_DIR = Path(__file__).resolve().parents[1]

# Uploaded PDFs, and the persisted ChromaDB vector store
DATA_DIR = BASE_DIR / "data"
CHROMA_DIR = BASE_DIR / "chroma_db"

# ChromaDB collection holding the document chunks
COLLECTION_NAME = "document_collection"

# Ollama inference server, and the model used for answer generation
OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2"

# How many retrieved chunks are passed to the LLM as context
MAX_CONTEXT_CHUNKS = 5

__all__ = [
    "BASE_DIR",
    "DATA_DIR",
    "CHROMA_DIR",
    "COLLECTION_NAME",
    "OLLAMA_URL",
    "DEFAULT_MODEL",
    "MAX_CONTEXT_CHUNKS",
]
