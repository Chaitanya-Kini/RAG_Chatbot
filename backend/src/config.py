from pathlib import Path
import os
from typing import Any

from dotenv import load_dotenv

# Load environment variables from a .env file if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]

# Allow overriding dirs via env vars, otherwise use defaults
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
CHROMA_DIR = Path(os.getenv("CHROMA_DIR", BASE_DIR / "chroma_db"))

# Collection name for the vector DB
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "document_collection")

# Embedding and LLM settings (safe defaults provided)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "llama3.2")

try:
	MAX_CONTEXT_CHUNKS: int = int(os.getenv("MAX_CONTEXT_CHUNKS", "5"))
except ValueError:
	MAX_CONTEXT_CHUNKS = 5

__all__ = [
	"BASE_DIR",
	"DATA_DIR",
	"CHROMA_DIR",
	"COLLECTION_NAME",
	"EMBEDDING_MODEL",
	"OLLAMA_URL",
	"DEFAULT_MODEL",
	"MAX_CONTEXT_CHUNKS",
]
