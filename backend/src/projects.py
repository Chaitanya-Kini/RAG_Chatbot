"""Project storage on disk.

A project is just a folder of PDFs under DATA_DIR:

    backend/data/
        Project 1/
            doc1.pdf
            doc2.pdf
        Project 2/
            doc4.pdf

Names are validated rather than escaped, so a client can never walk out of
DATA_DIR via "..", an absolute path, or a directory separator smuggled into a
project name or an upload filename.
"""

import re
import shutil
from pathlib import Path
from typing import Any, Dict, List

try:
    from .config import DATA_DIR
except ImportError:  # pragma: no cover
    from config import DATA_DIR

# Letters, digits, spaces, hyphens, underscores; must start with a letter or digit.
# This excludes ".", "/", "\\" and ".." by construction.
PROJECT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,63}$")


class ProjectError(ValueError):
    """Invalid project name, invalid filename, or a missing/conflicting target."""


class ProjectNotFound(ProjectError):
    """The named project does not exist on disk."""


def validate_project_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not PROJECT_NAME_RE.match(cleaned):
        raise ProjectError(
            "Project name must be 1-64 characters, start with a letter or digit, and "
            "contain only letters, digits, spaces, hyphens and underscores."
        )
    return cleaned


def safe_pdf_filename(filename: str) -> str:
    """Reduce a client-supplied filename to a bare .pdf leaf name."""
    # Path(...).name drops any directory component the client may have sent,
    # including Windows-style "..\\..\\evil.pdf".
    leaf = Path(filename or "").name.strip()
    if not leaf or leaf in {".", ".."}:
        raise ProjectError("Missing filename.")
    if not leaf.lower().endswith(".pdf"):
        raise ProjectError(f"'{leaf}' is not a PDF file.")
    return leaf


def project_dir(name: str) -> Path:
    return DATA_DIR / validate_project_name(name)


def existing_project_dir(name: str) -> Path:
    folder = project_dir(name)
    if not folder.is_dir():
        raise ProjectNotFound(f"Project '{folder.name}' does not exist.")
    return folder


def list_projects() -> List[str]:
    if not DATA_DIR.is_dir():
        return []
    return sorted(
        child.name
        for child in DATA_DIR.iterdir()
        if child.is_dir() and PROJECT_NAME_RE.match(child.name)
    )


def create_project(name: str) -> str:
    folder = project_dir(name)
    if folder.exists():
        raise ProjectError(f"Project '{folder.name}' already exists.")
    folder.mkdir(parents=True)
    return folder.name


def delete_project_files(name: str) -> None:
    shutil.rmtree(existing_project_dir(name))


def list_documents(name: str) -> List[Path]:
    return sorted(existing_project_dir(name).glob("*.pdf"))


def document_path(name: str, filename: str) -> Path:
    return existing_project_dir(name) / safe_pdf_filename(filename)


def save_upload(name: str, filename: str, content: bytes) -> str:
    destination = document_path(name, filename)
    destination.write_bytes(content)
    return destination.name


def delete_document_file(name: str, filename: str) -> None:
    path = document_path(name, filename)
    if not path.is_file():
        raise ProjectNotFound(f"'{path.name}' does not exist in project '{name}'.")
    path.unlink()


def describe_documents(name: str) -> List[Dict[str, Any]]:
    """Filenames and sizes for a project, without any index state."""
    return [
        {"filename": path.name, "size_bytes": path.stat().st_size}
        for path in list_documents(name)
    ]
