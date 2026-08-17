"""Thin HTTP client for the FastAPI backend.

Every call raises ApiError with a display-ready message, so the pages never have
to inspect status codes or catch requests exceptions themselves.
"""

from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests

API_URL = "http://127.0.0.1:8000"


class ApiError(RuntimeError):
    """A backend call failed, or the backend could not be reached."""


def _request(method: str, path: str, timeout: int = 60, **kwargs: Any) -> Dict[str, Any]:
    try:
        response = requests.request(method, f"{API_URL}{path}", timeout=timeout, **kwargs)
    except requests.RequestException as exc:
        raise ApiError(f"Cannot reach the backend at {API_URL}. Is it running?") from exc

    if not response.ok:
        detail = f"HTTP {response.status_code}"
        try:
            body = response.json()
            detail = body.get("detail") or body.get("message") or detail
            if isinstance(detail, list) and detail:
                # FastAPI validation errors arrive as a list of field errors.
                detail = detail[0].get("msg", str(detail))
        except ValueError:
            pass
        raise ApiError(str(detail))

    return response.json()


def _segment(value: str) -> str:
    """Percent-encode a path segment. Project names may contain spaces."""
    return quote(value, safe="")


def health() -> Dict[str, Any]:
    return _request("GET", "/health", timeout=5)


def is_online() -> bool:
    try:
        health()
        return True
    except ApiError:
        return False


def list_projects() -> List[Dict[str, Any]]:
    return _request("GET", "/projects").get("projects", [])


def create_project(name: str) -> Dict[str, Any]:
    return _request("POST", "/projects", json={"name": name})


def delete_project(name: str) -> Dict[str, Any]:
    return _request("DELETE", f"/projects/{_segment(name)}")


def list_documents(project: str) -> Dict[str, Any]:
    return _request("GET", f"/projects/{_segment(project)}/documents")


def upload_documents(project: str, files: List[Tuple[str, bytes]]) -> Dict[str, Any]:
    payload = [("files", (name, content, "application/pdf")) for name, content in files]
    return _request(
        "POST",
        f"/projects/{_segment(project)}/documents",
        files=payload,
        timeout=180,
    )


def ingest(project: str, filename: Optional[str] = None) -> Dict[str, Any]:
    params = {"filename": filename} if filename else None
    return _request(
        "POST",
        f"/projects/{_segment(project)}/ingest",
        params=params,
        timeout=600,
    )


def delete_document(project: str, filename: str) -> Dict[str, Any]:
    return _request(
        "DELETE",
        f"/projects/{_segment(project)}/documents",
        params={"filename": filename},
    )


def query(question: str, project: Optional[str] = None) -> Dict[str, Any]:
    """Ask a question. Without a project the model answers with no document context."""
    return _request(
        "POST",
        "/query",
        json={"question": question, "project": project},
        timeout=180,
    )
