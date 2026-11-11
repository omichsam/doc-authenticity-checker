"""
HTTP API for the document checker, so other systems (for example a Django project) can call the model.

Run locally:
    python -m uvicorn api:app --host 127.0.0.1 --port 8100
Set DOC_CHECKER_API_KEY to require an `X-API-Key` header on the /v1 endpoints. See API.md.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import queue
import re
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import pymupdf
from PIL import Image
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from tamper_core import QUALITY_FACTORS, Checker, draw_boxes, heat_overlay, load_image, quality, suspicious_regions

API_VERSION = "1.1"
HERE = Path(__file__).resolve().parent
MODEL_PATH = Path(os.environ.get("DOC_CHECKER_MODEL", HERE / "tamper_cnn.pt"))
REFERENCE_PATH = Path(os.environ.get("DOC_CHECKER_REFERENCE", HERE / "genuine_scores.json"))
API_KEY = os.environ.get("DOC_CHECKER_API_KEY", "")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024   # same limit as the Streamlit app
MAX_REGIONS = 10
MAX_PAGES = 20
PDF_DPI = 200
MAX_RENDER_SIDE = 4000                # caps the pixels rendered from an unusually large PDF page
MEDIUM_SHARE = 0.9                    # scoring higher than this share of real pages = "medium" level
CACHE_SIZE = 64                       # results remembered by file fingerprint
JOB_TTL_SECONDS = 6 * 3600            # finished background checks are kept this long
MAX_KEPT_JOBS = 500                   # ...but only the newest of them
MAX_QUEUED_JOBS = 20

NOTE = ("Screening aid only. A result never proves a document is genuine or forged; "
        "a trained person makes the final decision.")
MESSAGES = {
    "possible_changes": "Possible changes found. A person should check this page.",
    "borderline": "Nothing clear found, but the score is close to the warning level. This is common for real pages.",
    "no_signs": "No signs of changes found. Some kinds of changes can still be missed.",
    "poor_quality": "The picture is not clear enough. Ask for a clearer scan or photo; the change check is not "
                    "reliable on it.",
}
QUALITY_ADVICE = {
    "sharpness": "The picture is blurry. Retake it holding the camera steady, or use a scanner.",
    "contrast": "The writing is faint against the paper. Scan it in better light, or use a darker original.",
    "brightness": "The picture is too dark or too bright. Retake it in even light, without glare or shadows.",
    "resolution": "The picture is too small. Scan at 200–300 dpi, or photograph the page from closer.",
}
ACTION_RANK = {"continue": 0, "request_rescan": 1, "manual_review": 2}

log = logging.getLogger("doc_checker.api")
if not API_KEY and os.environ.get("DOC_CHECKER_REQUIRE_KEY") == "1":
    raise SystemExit("DOC_CHECKER_API_KEY must be set (DOC_CHECKER_REQUIRE_KEY=1).")
checker = Checker.load(MODEL_PATH)
MODEL_SHA256 = hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()
_predict_lock = threading.Lock()   # one page at a time: a single prediction already uses every CPU core
if not API_KEY:
    log.warning("DOC_CHECKER_API_KEY is not set: the API accepts requests without a key. Set it before deploying.")


def load_reference() -> np.ndarray | None:
    """Sorted scores of real held-out pages (from calibrate.py), if they belong to this model."""
    if not REFERENCE_PATH.exists():
        log.warning("%s not found: results will not compare pages with real ones.", REFERENCE_PATH.name)
        return None
    data = json.loads(REFERENCE_PATH.read_text())
    if data.get("model_sha256") != MODEL_SHA256 or not data.get("scores"):
        log.warning("%s was made for another model: run calibrate.py again.", REFERENCE_PATH.name)
        return None
    return np.sort(np.asarray(data["scores"], dtype=np.float64))


REFERENCE = load_reference()


class DocumentError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code = status, code


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def unauthorised(request: Request) -> JSONResponse | None:
    if API_KEY and not hmac.compare_digest(request.headers.get("x-api-key", ""), API_KEY):
        return error(401, "invalid_api_key", "Send a valid key in the X-API-Key header.")
    return None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# --------------------------------------------------------------------------- reading the upload
def read_pages(data: bytes) -> tuple[str, list[np.ndarray]]:
    """Decode an upload into RGB page images: one for an image, one per page for a PDF."""
    if data[:5] == b"%PDF-":
        return "pdf", pdf_pages(data)
    try:
        return "image", [load_image(data)]
    except Image.DecompressionBombError:
        raise DocumentError(413, "image_too_large", "The image has too many pixels to check safely.")
    except ValueError:
        raise DocumentError(415, "unsupported_file",
                            "The file could not be read. Send a PDF or an image (PNG, JPG, WEBP, TIFF or BMP).")


def pdf_pages(data: bytes) -> list[np.ndarray]:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:   # PyMuPDF raises several error types for damaged files
        raise DocumentError(415, "unsupported_file", "The PDF could not be opened. It may be damaged.")
    with doc:
        if doc.needs_pass:
            raise DocumentError(415, "encrypted_pdf", "The PDF is password-protected. Send an unprotected copy.")
        if doc.page_count == 0:
            raise DocumentError(415, "unsupported_file", "The PDF has no pages.")
        if doc.page_count > MAX_PAGES:
            raise DocumentError(413, "too_many_pages", f"The PDF has {doc.page_count} pages; the limit is {MAX_PAGES}.")
        pages = []
        try:
            for page in doc:
                zoom = min(PDF_DPI / 72, MAX_RENDER_SIDE / max(page.rect.width, page.rect.height, 1))
                pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csRGB, alpha=False)
                pages.append(np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3).copy())
        except Exception:
            raise DocumentError(415, "unsupported_file", "A page of the PDF could not be read. It may be damaged.")
    return pages


# --------------------------------------------------------------------------- checking pages
def higher_than_pct(score: float) -> int | None:
    if REFERENCE is None:
        return None
    return int(100 * np.searchsorted(REFERENCE, score, side="left") / len(REFERENCE))


def page_reasons(q_score, q_cat, advice, score, thr, pct, n_hot) -> list[str]:
    if q_cat == "POOR":
        reasons = [f"Picture quality is POOR ({q_score:.0f}/100), so the change check is not reliable. {advice}"]
    elif q_cat == "ACCEPTABLE":
        reasons = [f"Picture quality is ACCEPTABLE ({q_score:.0f}/100): usable, but the change check is less "
                   "reliable than on a clear picture."]
    else:
        reasons = [f"Picture quality is GOOD ({q_score:.0f}/100), so the change check is reliable."]
    if score >= thr:
        reasons.append(f"The most unusual spot scored {score:.3f}, at or above the warning level of {thr:.3f}.")
        reasons.append(f"{n_hot} spot{'s' if n_hot != 1 else ''} reached the warning level; "
                       "box 1 is the most suspicious.")
    else:
        reasons.append(f"The most unusual spot scored {score:.3f}, below the warning level of {thr:.3f}.")
    if pct is not None:
        tail = ("." if score >= thr else
                " — unusual for a genuine page, but below the warning level." if pct >= MEDIUM_SHARE * 100 else
                " — normal for a genuine page.")
        reasons.append(f"That is higher than {pct}% of {len(REFERENCE)} real test pages{tail}")
    return reasons


def analyse_page(img: np.ndarray, include_heatmap: bool) -> dict:
    q_score, q_cat, q_parts = quality(img)
    with _predict_lock:
        work, prob, score = checker.predict(img)

    thr = checker.threshold
    verdict = "possible_changes" if score >= thr else "borderline" if score >= thr * 0.7 else "no_signs"
    pct = higher_than_pct(score)
    if score >= thr:
        level = "high"
    elif pct is not None:
        level = "medium" if pct >= MEDIUM_SHARE * 100 else "low"
    else:
        level = "medium" if verdict == "borderline" else "low"
    weakest = max(q_parts, key=lambda k: QUALITY_FACTORS[k][0] * (1 - q_parts[k]))
    advice = None if q_cat == "GOOD" else QUALITY_ADVICE[weakest]
    if q_cat == "POOR":
        action, message = "request_rescan", MESSAGES["poor_quality"]
    else:
        action, message = ("manual_review" if verdict == "possible_changes" else "continue"), MESSAGES[verdict]

    regions = suspicious_regions(prob, thr=0.5)[:MAX_REGIONS]
    height, width = img.shape[:2]
    scale = width / work.shape[1]   # report boxes in the uploaded page's own pixels
    boxes = []
    for x, y, w, h, p in regions:
        x, y, w, h = round(x * scale), round(y * scale), round(w * scale), round(h * scale)
        boxes.append({"x": x, "y": y, "width": w, "height": h,
                      "x_pct": round(100 * x / width, 2), "y_pct": round(100 * y / height, 2),
                      "width_pct": round(100 * w / width, 2), "height_pct": round(100 * h / height, 2),
                      "peak": round(p, 4)})
    n_hot = sum(1 for *_, p in regions if p >= thr)

    page = {
        "action": action,
        "level": level,
        "message": message,
        "reasons": page_reasons(q_score, q_cat, advice, score, thr, pct, n_hot),
        "quality": {"score": round(q_score, 1), "category": q_cat, "advice": advice,
                    "parts": {k: round(v, 3) for k, v in q_parts.items()}},
        "change": {
            "score": round(score, 4),
            "verdict": verdict,
            "warning_level": round(thr, 5),
            "compared_to_real_pages": None if pct is None else {"higher_than_pct": pct, "pages": len(REFERENCE)},
            "regions": boxes,
        },
        "image": {"width": width, "height": height},
    }
    if include_heatmap:
        overlay = draw_boxes(heat_overlay(work, prob), regions)
        ok, png = cv2.imencode(".png", cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))
        page["heatmap_png_base64"] = base64.b64encode(png.tobytes()).decode("ascii") if ok else None
    return page


def analyse_document(kind: str, imgs: list[np.ndarray], include_heatmap: bool) -> dict:
    """Check every page; the document takes the result of its worst page."""
    pages = [analyse_page(img, include_heatmap) for img in imgs]
    worst = max(range(len(pages)), key=lambda i: (ACTION_RANK[pages[i]["action"]], pages[i]["change"]["score"]))
    w = pages[worst]
    message, reasons = w["message"], list(w["reasons"])
    if len(pages) > 1:
        message = f"Page {worst + 1}: {message}"
        review = [str(i + 1) for i, p in enumerate(pages) if p["action"] == "manual_review"]
        rescan = [str(i + 1) for i, p in enumerate(pages) if p["action"] == "request_rescan"]
        summary = f"{len(pages)} pages checked; page {worst + 1} decides the result."
        if review:
            summary += f" Pages to review: {', '.join(review)}."
        if rescan:
            summary += f" Pages needing a clearer picture: {', '.join(rescan)}."
        reasons.insert(0, summary)
    for i, p in enumerate(pages, 1):
        p["page"] = i
    result = {
        "action": w["action"],
        "level": w["level"],
        "message": message,
        "reasons": reasons,
        "quality": w["quality"],
        "change": w["change"],
        "image": w["image"],
        "page_count": len(pages),
        "worst_page": worst + 1,
        "pages": pages,
        "model": {"sha256": MODEL_SHA256, "device": checker.device.type},
        "note": NOTE,
    }
    if include_heatmap:
        result["heatmap_png_base64"] = w["heatmap_png_base64"]
        if len(pages) == 1:   # don't send the same picture twice
            del pages[0]["heatmap_png_base64"]
    return result


# --------------------------------------------------------------------------- remembering results
_cache: OrderedDict[tuple[str, bool], dict] = OrderedDict()
_cache_lock = threading.Lock()


def cache_get(sha: str, include_heatmap: bool) -> dict | None:
    with _cache_lock:
        hit = _cache.get((sha, include_heatmap))
        if hit is not None:
            _cache.move_to_end((sha, include_heatmap))
        return hit


def cache_put(sha: str, include_heatmap: bool, analysis: dict) -> None:
    with _cache_lock:
        _cache[(sha, include_heatmap)] = analysis
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)


def finish(analysis: dict, check_id: str, file_info: dict, cached: bool, started: float) -> dict:
    """Wrap a page analysis with the details of this particular request."""
    return {"check_id": check_id, "checked_at": now_iso(), "api_version": API_VERSION, "file": file_info,
            **analysis, "cached": cached, "elapsed_ms": round((time.perf_counter() - started) * 1000)}


def check_now(data: bytes, filename: str, include_heatmap: bool, check_id: str | None = None) -> dict:
    started = time.perf_counter()
    check_id = check_id or f"chk_{uuid.uuid4().hex[:20]}"
    sha = hashlib.sha256(data).hexdigest()
    file_info = {"name": filename, "sha256": sha, "size_bytes": len(data)}
    if (hit := cache_get(sha, include_heatmap)) is not None:
        return finish(hit, check_id, {**file_info, **hit["_file"]}, True, started)
    kind, imgs = read_pages(data)
    analysis = analyse_document(kind, imgs, include_heatmap)
    analysis["_file"] = {"type": kind, "pages": len(imgs)}
    cache_put(sha, include_heatmap, analysis)
    return finish(analysis, check_id, {**file_info, **analysis["_file"]}, False, started)


def public(result: dict) -> dict:
    return {k: v for k, v in result.items() if k != "_file"}


# --------------------------------------------------------------------------- background checks
_jobs: OrderedDict[str, dict] = OrderedDict()
_jobs_lock = threading.Lock()
_job_queue: queue.Queue = queue.Queue()


def job_view(job: dict) -> dict:
    view = {"check_id": job["check_id"], "status": job["status"], "created_at": job["created_at"],
            "finished_at": job["finished_at"], "status_url": f"/v1/checks/{job['check_id']}"}
    if job["status"] == "done":
        view["result"] = job["result"]
    elif job["status"] == "failed":
        view["error"] = job["error"]
    return view


def forget_old_jobs() -> None:
    cutoff = time.time() - JOB_TTL_SECONDS
    finished = [k for k, j in _jobs.items() if j["finished_ts"]]   # oldest first
    for i, check_id in enumerate(finished):
        if _jobs[check_id]["finished_ts"] < cutoff or len(finished) - i > MAX_KEPT_JOBS:
            del _jobs[check_id]


def worker() -> None:
    while True:
        check_id, data, filename, include_heatmap = _job_queue.get()
        with _jobs_lock:
            job = _jobs.get(check_id)
            if job is None:
                continue
            job["status"] = "running"
        try:
            result, status, err = public(check_now(data, filename, include_heatmap, check_id)), "done", None
        except DocumentError as exc:
            result, status, err = None, "failed", {"code": exc.code, "message": str(exc)}
        except Exception:
            log.exception("Background check %s failed", check_id)
            result, status, err = None, "failed", {"code": "internal_error", "message": "The check failed unexpectedly."}
        with _jobs_lock:
            job.update(status=status, result=result, error=err, finished_at=now_iso(), finished_ts=time.time())


threading.Thread(target=worker, name="doc-checker-worker", daemon=True).start()


def create_job(data: bytes, filename: str, include_heatmap: bool) -> dict:
    sha = hashlib.sha256(data).hexdigest()
    if cache_get(sha, include_heatmap) is None:
        read_pages(data)   # reject a bad file now rather than in the background
    check_id = f"chk_{uuid.uuid4().hex[:20]}"
    job = {"check_id": check_id, "status": "queued", "created_at": now_iso(), "finished_at": None,
           "finished_ts": None, "result": None, "error": None}
    with _jobs_lock:
        forget_old_jobs()
        if _job_queue.qsize() >= MAX_QUEUED_JOBS:
            raise DocumentError(503, "busy", "Too many checks are waiting. Try again in a few minutes.")
        _jobs[check_id] = job
    _job_queue.put((check_id, data, filename, include_heatmap))
    return job


# --------------------------------------------------------------------------- endpoints
async def read_upload(request: Request) -> tuple[bytes, str] | JSONResponse:
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > MAX_UPLOAD_BYTES + 64 * 1024:
        return error(413, "file_too_large", "The file is larger than 25 MB.")
    if not request.headers.get("content-type", "").startswith("multipart/form-data"):
        return error(400, "missing_file", "Send the document as multipart/form-data in a field named 'file'.")
    async with request.form(max_files=1, max_fields=5) as form:
        upload = form.get("file")
        if upload is None or isinstance(upload, str):
            return error(400, "missing_file", "Send the document as multipart/form-data in a field named 'file'.")
        data, filename = await upload.read(), upload.filename or "document"
    if len(data) > MAX_UPLOAD_BYTES:
        return error(413, "file_too_large", "The file is larger than 25 MB.")
    if not data:
        return error(400, "empty_file", "The uploaded file is empty.")
    return data, filename


def wants_heatmap(request: Request) -> bool:
    return request.query_params.get("heatmap", "").lower() in {"1", "true", "yes"}


ENDPOINTS = [
    {"method": "GET", "path": "/health", "key": False, "does": "Is the API up?"},
    {"method": "GET", "path": "/v1/model", "key": True, "does": "Model file, version and warning level."},
    {"method": "POST", "path": "/v1/checks", "key": True,
     "does": "Start a background check of an image or PDF (form field 'file'); returns a check_id at once."},
    {"method": "GET", "path": "/v1/checks/{check_id}", "key": True, "does": "Status and result of a background check."},
    {"method": "POST", "path": "/v1/check", "key": True, "does": "Check an image or PDF and wait for the result."},
]


async def index(request: Request) -> JSONResponse:
    return JSONResponse({"service": "PWD document checker API", "api_version": API_VERSION,
                         "auth": "Send the key in the X-API-Key header for endpoints marked key: true.",
                         "endpoints": ENDPOINTS, "docs": "See API.md in the project."})


async def not_found(request: Request, exc: Exception) -> JSONResponse:
    return error(404, "not_found", f"There is nothing at {request.url.path}. GET / lists the endpoints.")


def _matches(pattern: str, path: str) -> bool:
    return re.fullmatch(re.sub(r"\{[^/]+\}", "[^/]+", pattern), path) is not None


async def method_not_allowed(request: Request, exc: Exception) -> JSONResponse:
    allowed = sorted({e["method"] for e in ENDPOINTS if _matches(e["path"], request.url.path)})
    return error(405, "method_not_allowed", f"{request.method} is not allowed at {request.url.path}; use "
                                            f"{' or '.join(allowed)}. GET / lists the endpoints.")


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


async def model_info(request: Request) -> JSONResponse:
    if (denied := unauthorised(request)) is not None:
        return denied
    return JSONResponse({"api_version": API_VERSION, "file": MODEL_PATH.name, "sha256": MODEL_SHA256,
                         "device": checker.device.type, "warning_level": round(checker.threshold, 5),
                         "real_pages_for_comparison": None if REFERENCE is None else len(REFERENCE),
                         "trained_at": checker.meta.get("trained_at"), "test": checker.meta.get("test")})


async def check(request: Request) -> JSONResponse:
    """Check a document and wait for the result."""
    if (denied := unauthorised(request)) is not None:
        return denied
    upload = await read_upload(request)
    if isinstance(upload, JSONResponse):
        return upload
    try:
        result = await run_in_threadpool(check_now, *upload, wants_heatmap(request))
    except DocumentError as exc:
        return error(exc.status, exc.code, str(exc))
    return JSONResponse(public(result))


async def submit_check(request: Request) -> JSONResponse:
    """Start a background check and return at once; fetch the result from status_url."""
    if (denied := unauthorised(request)) is not None:
        return denied
    upload = await read_upload(request)
    if isinstance(upload, JSONResponse):
        return upload
    try:
        job = await run_in_threadpool(create_job, *upload, wants_heatmap(request))
    except DocumentError as exc:
        return error(exc.status, exc.code, str(exc))
    with _jobs_lock:
        view = job_view(job)
    return JSONResponse(view, status_code=202, headers={"Location": view["status_url"]})


async def get_check(request: Request) -> JSONResponse:
    if (denied := unauthorised(request)) is not None:
        return denied
    with _jobs_lock:
        forget_old_jobs()
        job = _jobs.get(request.path_params["check_id"])
        view = job_view(job) if job else None
    if view is None:
        return error(404, "check_not_found", "No check with this id. Results are kept for 6 hours and are lost "
                                             "when the API restarts; send the document again.")
    return JSONResponse(view)


app = Starlette(exception_handlers={404: not_found, 405: method_not_allowed}, routes=[
    Route("/", index),
    Route("/health", health),
    Route("/v1/model", model_info),
    Route("/v1/check", check, methods=["POST"]),
    Route("/v1/checks", submit_check, methods=["POST"]),
    Route("/v1/checks/{check_id}", get_check),
])
