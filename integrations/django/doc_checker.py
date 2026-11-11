"""
Client for the document-checker API. Copy this file into your Django project (for example `yourapp/doc_checker.py`).

Settings it reads (with environment-variable fallbacks):
    DOC_CHECKER_URL      e.g. "http://127.0.0.1:8100"
    DOC_CHECKER_API_KEY  the key the API was started with
    DOC_CHECKER_TIMEOUT  seconds to wait for a check that you wait for (default 120)

Usage:
    from .doc_checker import check_document, submit_check, get_check, DocCheckerError

    result = check_document(document.file)    # wait for the result
    result["action"]   # "continue" | "manual_review" | "request_rescan"

    job = submit_check(document.file)         # or: start in the background, returns at once
    job = get_check(job["check_id"])          # later: job["status"] is "queued", "running", "done" or "failed"
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

import requests

try:
    from django.conf import settings as _settings
except ImportError:   # lets the client be used (and tested) outside Django
    _settings = None


class DocCheckerError(Exception):
    """The check could not be done: the API is unreachable, rejected the file, or failed."""

    def __init__(self, message: str, code: str = "unavailable", status: int | None = None):
        super().__init__(message)
        self.code, self.status = code, status


def _setting(name: str, default: str = "") -> str:
    if _settings is not None and _settings.configured and hasattr(_settings, name):
        return str(getattr(_settings, name))
    return os.environ.get(name, default)


def _read(file, filename: str | None) -> tuple[bytes, str]:
    if isinstance(file, (bytes, bytearray)):
        return bytes(file), filename or "document"
    if getattr(file, "closed", False) and hasattr(file, "open"):   # e.g. a saved model FileField
        file.open("rb")
    file.seek(0)
    return file.read(), filename or Path(getattr(file, "name", "") or "document").name


def _call(method: str, path: str, *, timeout: float = 30, **kwargs) -> dict:
    url = _setting("DOC_CHECKER_URL", "http://127.0.0.1:8100").rstrip("/") + path
    try:
        response = requests.request(method, url, headers={"X-API-Key": _setting("DOC_CHECKER_API_KEY")},
                                    timeout=timeout, **kwargs)
    except requests.RequestException as exc:
        raise DocCheckerError(f"The document checker could not be reached: {exc}") from exc
    try:
        body = response.json()
    except ValueError:
        raise DocCheckerError(f"The document checker returned an unexpected response ({response.status_code}).",
                              status=response.status_code)
    if response.status_code not in (200, 202):
        err = body.get("error", {})
        raise DocCheckerError(err.get("message", "The check failed."), err.get("code", "error"), response.status_code)
    return body


def check_document(file, *, filename: str | None = None, heatmap: bool = False) -> dict:
    """Send a document (image or PDF) and wait for the result. Raises DocCheckerError on any failure."""
    data, name = _read(file, filename)
    return _call("POST", "/v1/check", params={"heatmap": "true"} if heatmap else None,
                 files={"file": (name, data, "application/octet-stream")},
                 timeout=float(_setting("DOC_CHECKER_TIMEOUT", "120")))


def submit_check(file, *, filename: str | None = None, heatmap: bool = False) -> dict:
    """Start a background check and return at once with its check_id. Raises DocCheckerError on any failure."""
    data, name = _read(file, filename)
    return _call("POST", "/v1/checks", params={"heatmap": "true"} if heatmap else None,
                 files={"file": (name, data, "application/octet-stream")})


def get_check(check_id: str) -> dict:
    """Status of a background check: "queued", "running", "done" (with "result") or "failed" (with "error").

    Raises DocCheckerError with code "check_not_found" if the API no longer has it (kept 6 hours, lost on restart).
    """
    return _call("GET", f"/v1/checks/{check_id}")


def heatmap_bytes(result: dict) -> bytes | None:
    """PNG bytes of the colour map, if the check was made with heatmap=True."""
    encoded = result.get("heatmap_png_base64")
    return base64.b64decode(encoded) if encoded else None
