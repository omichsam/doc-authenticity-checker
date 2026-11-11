# Document checker API — Django integration

The API lets another system, such as a Django project, send a document and
get the check result back as JSON. It runs the same model and rules as the
Streamlit app (the same quality score, change score and warning level), and
also explains each result.

```text
Django project ──POST /v1/checks (image or PDF)──▶ document-checker API (api.py + tamper_cnn.pt)
      │                    ◀── 202 + check_id ───────────────┘   (returns at once)
      └──GET /v1/checks/{check_id}──▶ queued / running / done + JSON result
```

> **Screening aid only.** Use the result to *route* a document, for example
> to a reviewer queue. Never use it to reject a document automatically. A
> trained person makes the decision.

---

## 1. Run the API

### Locally (Windows, for development)

```powershell
cd C:\path\to\simple_cnn
$env:DOC_CHECKER_API_KEY = "choose-a-long-random-key"
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8100
```

Port **8100** is used so it doesn't clash with Django's `runserver` on 8000.
Check that it's running: <http://127.0.0.1:8100/health> should return
`{"status": "ok"}`.

### With Docker (on a server)

```bash
export DOC_CHECKER_API_KEY="choose-a-long-random-key"
docker compose --profile api up -d --build
```

- This starts the Streamlit app (port 8501) and the API (port 8100).
- The API container refuses to start without `DOC_CHECKER_API_KEY`.
- The API port is published on `127.0.0.1` only, so only programs on the same
  server can reach it.
- If Django runs on another machine, put the API behind HTTPS (for example
  Nginx) and limit access to Django's address. If Django runs in the same
  Compose project, call it at `http://document-checker-api:8100` and remove
  the `ports:` entry.

Plain `docker compose up` still starts only the Streamlit app, as before.

### Settings

| Environment variable | Default | Meaning |
| --- | --- | --- |
| `DOC_CHECKER_API_KEY` | *(none)* | Required `X-API-Key` value for `/v1/...` calls. If it's not set, the API accepts calls without a key and logs a warning. **Always set it outside your own computer.** |
| `DOC_CHECKER_REQUIRE_KEY` | *(off)* | `1` = refuse to start without a key (Docker sets this). |
| `DOC_CHECKER_MODEL` | `tamper_cnn.pt` next to `api.py` | Path to the model file. |
| `DOC_CHECKER_REFERENCE` | `genuine_scores.json` next to `api.py` | Scores of real pages that results are compared with (made by `calibrate.py`). |

**Speed:** one page takes **about 5–20 seconds on a CPU**, depending on the
machine. The API checks one page at a time. Use background checks
(`POST /v1/checks`) so nobody waits. A file that has been checked before is
answered from memory at once.

**After retraining the model,** run `python calibrate.py` (it needs the
notebook's `data/` folder). This refreshes `genuine_scores.json`. Until you
do, results leave out the comparison with real pages, and the API logs a
warning.

---

## 2. Endpoints

| Method and path | Key needed | What it does |
| --- | --- | --- |
| `GET /` | No | A short overview: the API version and the list of endpoints. This is what you see if you open the API's address in a browser. |
| `GET /health` | No | `{"status": "ok"}` when the API is up. For monitoring. |
| `GET /v1/model` | Yes | API version, model file and SHA-256, device, warning level, and how many real pages results are compared with. |
| `POST /v1/checks` | Yes | **Start a background check** and return at once (202) with a `check_id`. |
| `GET /v1/checks/{check_id}` | Yes | Status of a background check (`queued`, `running`, `done` or `failed`), with the result when it's done. |
| `POST /v1/check` | Yes | Check a document and **wait** for the result (simplest, but slow). |

For every `POST`, send the file as `multipart/form-data` in a field named
**`file`**:

- **Formats:** an image (PNG, JPG, WEBP, TIFF, BMP) or a **PDF** of up to
  20 pages. Each PDF page is checked separately.
- **Size:** up to 25 MB.
- **Heat map:** add `?heatmap=true` to also get the colour map.

```bash
# start a check
curl -H "X-API-Key: $DOC_CHECKER_API_KEY" -F "file=@application.pdf" http://127.0.0.1:8100/v1/checks
# → 202 {"check_id": "chk_…", "status": "queued", "status_url": "/v1/checks/chk_…", …}

# a few seconds later
curl -H "X-API-Key: $DOC_CHECKER_API_KEY" http://127.0.0.1:8100/v1/checks/chk_…
# → {"check_id": "chk_…", "status": "done", "finished_at": "…", "result": { …the result below… }}
```

Background checks are kept in memory for **6 hours**, and the newest 500 are
kept. They are lost when the API restarts. If `GET` returns 404
`check_not_found`, send the document again.

### The result

A real result, for a page whose date had been changed. Each `pages` entry has the same fields as the top level, for its own page; it is shortened here:

```json
{
  "check_id": "chk_5ad52e795be74eb2a03d",
  "checked_at": "2026-11-11T07:26:15Z",
  "api_version": "1.1",
  "file": {
    "name": "page1.jpg",
    "sha256": "1a2312657d43…",
    "size_bytes": 134784,
    "type": "image",
    "pages": 1
  },
  "action": "manual_review",
  "level": "high",
  "message": "Possible changes found. A person should check this page.",
  "reasons": [
    "Picture quality is ACCEPTABLE (62/100): usable, but the change check is less reliable than on a clear picture.",
    "The most unusual spot scored 0.998, at or above the warning level of 0.995.",
    "1 spot reached the warning level; box 1 is the most suspicious.",
    "That is higher than 99% of 122 real test pages."
  ],
  "quality": {
    "score": 61.8,
    "category": "ACCEPTABLE",
    "advice": "The picture is blurry. Retake it holding the camera steady, or use a scanner.",
    "parts": {"sharpness": 0.65, "contrast": 0.466, "brightness": 0.491, "resolution": 0.905}
  },
  "change": {
    "score": 0.9978,
    "verdict": "possible_changes",
    "warning_level": 0.99497,
    "compared_to_real_pages": {
      "higher_than_pct": 99,
      "pages": 122
    },
    "regions": [
      {"x": 100, "y": 159, "width": 120, "height": 19, "x_pct": 13.81, "y_pct": 15.53, "width_pct": 16.57, "height_pct": 1.86, "peak": 0.9984},
      {"x": 60, "y": 450, "width": 28, "height": 8, "x_pct": 8.29, "y_pct": 43.95, "width_pct": 3.87, "height_pct": 0.78, "peak": 0.7233}
    ]
  },
  "image": {
    "width": 724,
    "height": 1024
  },
  "page_count": 1,
  "worst_page": 1,
  "pages": [
    {"page": 1, "action": "manual_review", "level": "high", "message": "…", "reasons": ["…"],
     "quality": {"…": "…"}, "change": {"…": "…"}, "image": {"…": "…"}}
  ],
  "model": {
    "sha256": "c0fb0cfeb745…",
    "device": "cpu"
  },
  "note": "Screening aid only. A result never proves a document is genuine or forged; a trained person makes the final decision.",
  "cached": false,
  "elapsed_ms": 17932
}
```

#### Fields for deciding

| Field | Meaning |
| --- | --- |
| **`action`** | **What your system should do.** `continue` = normal flow · `manual_review` = send to a reviewer · `request_rescan` = ask the applicant for a clearer picture. |
| **`level`** | How unusual the page looks: `low`, `medium` or `high`. `high` = reached the warning level. `medium` = higher than 90% of real pages, but below the warning level. `low` = like most real pages. Handy for sorting a reviewer queue. |
| `message` | The result in one plain sentence, ready to show to staff. For a PDF it starts with the page it's about ("Page 2: …"). |
| **`reasons`** | Why this `action` was chosen, in plain sentences: picture quality, the score against the warning level, and the comparison with real pages. Show these to reviewers. |

#### Picture quality

| Field | Meaning |
| --- | --- |
| `quality.score` / `category` | Picture clarity 0–100: `GOOD` (≥ 70), `ACCEPTABLE` (40–69) or `POOR` (< 40). `POOR` always gives `request_rescan`. |
| `quality.advice` | For ACCEPTABLE and POOR pictures: what to tell the applicant, for example "The picture is blurry. Retake it holding the camera steady, or use a scanner." `null` for GOOD pictures. |
| `quality.parts` | Sharpness, contrast, brightness and resolution, each 0–1. |

#### The change check

| Field | Meaning |
| --- | --- |
| `change.score` | 0–1, the score of the most unusual spot on the page. **Not** the chance that the document is fake. Real pages often score 0.7–0.99. |
| `change.verdict` | `possible_changes` (score ≥ warning level), `borderline` (≥ 70% of the warning level, which is normal for real pages) or `no_signs`. |
| `change.compared_to_real_pages` | `higher_than_pct`: the share of real test pages (never used in training) that scored lower than this page. `pages`: how many there were. `null` if `genuine_scores.json` is missing or out of date. |
| `change.regions` | Up to 10 boxes around spots scoring ≥ 0.5, most suspicious first. `x`, `y`, `width`, `height` are in the page's own pixels. `x_pct` … `height_pct` are percentages of the page, so you can draw them on the page at any size. `peak` is that spot's score. Boxes appear on real pages too. |

#### The file and the check

| Field | Meaning |
| --- | --- |
| `check_id`, `checked_at` | Unique id and UTC time of this check. Store them for audit. |
| `api_version` | `1.1`. |
| `file` | `name`, `sha256` (fingerprint of the uploaded bytes), `size_bytes`, `type` (`image` or `pdf`), `pages`. |
| `page_count`, `worst_page`, `pages` | Every page's own result (the same fields, plus `page`). The top-level fields are those of the **worst page**: `manual_review` beats `request_rescan`, which beats `continue`, and ties go to the higher score. |
| `model.sha256` | Identifies the exact model file. Store it with the result. |
| `cached` | `true` if the same file was checked recently and the result came from memory. It still gets its own `check_id`. |
| `elapsed_ms` | Time this request took. |
| `heatmap_png_base64` | Only with `?heatmap=true`: the worst page's colour map with boxes, as a base64 PNG (about 0.5 MB). For a PDF, each `pages[]` entry also has its own. |

Every field from version 1.0 is still there and means the same thing, so
older callers keep working.

### Errors

Errors return a status code and a body like
`{"error": {"code": "...", "message": "..."}}`:

| Status | `code` | Cause |
| --- | --- | --- |
| 400 | `missing_file` / `empty_file` | No `file` field in a multipart body, or the file is empty. |
| 401 | `invalid_api_key` | Missing or wrong `X-API-Key`. |
| 404 | `check_not_found` | Unknown or expired `check_id` (kept 6 hours, lost on restart). Send the document again. |
| 404 | `not_found` | Nothing at that address, for example a typo in the path. `GET /` lists the endpoints. |
| 405 | `method_not_allowed` | Wrong method for the address, for example opening `/v1/check` in a browser (a `GET`) when it needs a `POST` with a file. The message says which method to use. |
| 413 | `file_too_large` / `image_too_large` / `too_many_pages` | Over 25 MB, too many pixels, or more than 20 PDF pages. |
| 415 | `unsupported_file` / `encrypted_pdf` | Not a readable image or PDF, or a password-protected PDF. |
| 503 | `busy` | 20 background checks are already waiting. Try again in a few minutes. |

For background checks, an unreadable file is refused at once with the same
error. A check that fails later has `"status": "failed"` and an `error`
object.

### Test with Postman

The [postman/](postman/) folder has a ready-made collection: every endpoint
and every error case, with automatic checks on each response.

1. In Postman, click **Import** and choose both files:
   - `postman/PWD Document Checker API.postman_collection.json`
   - `postman/environments/PWD Document Checker - local.postman_environment.json`
2. Select the **PWD Document Checker - local** environment (top right). Put
   the key the API was started with into **`apiKey`**.
3. Uploads use the sample files in `postman/files/`. The page images aren't
   in the repository (they come from a dataset), so add your own first. See
   [postman/files/README.md](postman/files/README.md). In **Settings → General
   → Working directory**, choose this project folder (`simple_cnn`), so
   Postman can find them. Otherwise, pick the file again in a request's
   **Body** tab.
4. Right-click the collection and choose **Run collection** to run them all
   in order. Some requests use results from earlier ones. Or open a request
   and click **Send**, then look at **Test Results**.

Two requests have extras:

- **Edited page with heat map:** open the **Visualize** tab to see the
  colour map and the reasons.
- **Get the background check result:** if you click **Send** yourself, click
  it again until the status is `done`. In a collection run it repeats by
  itself.

From a terminal (Postman CLI):

```powershell
postman collection run "postman/PWD Document Checker API.postman_collection.json" `
  -e "postman/environments/PWD Document Checker - local.postman_environment.json" `
  --env-var "apiKey=YOUR-KEY" --working-dir . --timeout-request 180000
```

---

## 3. Add it to your Django project

The steps below were tested together in a fresh Django project against the
running API.

**Using an AI coding assistant?**
[integrations/django/INTEGRATION_PROMPT.md](integrations/django/INTEGRATION_PROMPT.md)
is a ready-made prompt. It asks the assistant to fit these steps into your
existing Django models and views, with tests.

**How it works:**

1. The upload *starts* a background check, which takes less than a second.
2. The document page asks the API for the result when someone opens it.
3. While the check is running, the page refreshes itself every 5 seconds.

This needs no Celery or other task queue.

### 3.1 Install and configure

```bash
pip install requests
```

Copy [integrations/django/doc_checker.py](integrations/django/doc_checker.py)
into your app, for example `documents/doc_checker.py`. Then add to
`settings.py`:

```python
import os

DOC_CHECKER_URL = os.environ.get("DOC_CHECKER_URL", "http://127.0.0.1:8100")
DOC_CHECKER_API_KEY = os.environ["DOC_CHECKER_API_KEY"]   # same key the API was started with
DOC_CHECKER_TIMEOUT = 120                                  # seconds, only for check_document() (waits)
```

Keep the key in an environment variable or your secrets store, **not** in Git.

### 3.2 Store the result with the document (`models.py`)

```python
from django.db import models


class Document(models.Model):
    class CheckStatus(models.TextChoices):
        PENDING = "pending", "Waiting for check"
        DONE = "done", "Checked"
        FAILED = "failed", "Check failed"

    class CheckAction(models.TextChoices):
        CONTINUE = "continue", "No action needed"
        MANUAL_REVIEW = "manual_review", "Send for manual review"
        REQUEST_RESCAN = "request_rescan", "Ask for a clearer scan"

    file = models.FileField(upload_to="documents/%Y/%m/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    check_id = models.CharField(max_length=40, blank=True)        # the API's id for the running check
    check_status = models.CharField(max_length=10, choices=CheckStatus.choices, default=CheckStatus.PENDING)
    check_action = models.CharField(max_length=20, choices=CheckAction.choices, blank=True)
    check_level = models.CharField(max_length=10, blank=True)      # low / medium / high
    check_message = models.CharField(max_length=255, blank=True)
    check_result = models.JSONField(null=True, blank=True)       # the full API result (without the heat map)
    check_heatmap = models.FileField(upload_to="heatmaps/%Y/%m/", blank=True)
    check_error = models.TextField(blank=True)
    checked_at = models.DateTimeField(null=True, blank=True)
```

Then run `python manage.py makemigrations` and `python manage.py migrate`.

### 3.3 Starting a check and collecting its result (`services.py`)

```python
from django.core.files.base import ContentFile
from django.utils import timezone

from .doc_checker import DocCheckerError, check_document, get_check, heatmap_bytes, submit_check
from .models import Document


def save_result(doc: Document, result: dict) -> None:
    png = heatmap_bytes(result)
    result = {k: v for k, v in result.items() if k != "heatmap_png_base64"}   # keep big images out of the row
    for page in result.get("pages", []):
        page.pop("heatmap_png_base64", None)
    if png:
        doc.check_heatmap.save(f"document-{doc.pk}.png", ContentFile(png), save=False)
    doc.check_status = Document.CheckStatus.DONE
    doc.check_action = result["action"]
    doc.check_level = result["level"]
    doc.check_message = result["message"]
    doc.check_result = result
    doc.check_error = ""
    doc.checked_at = timezone.now()
    doc.save()


def mark_failed(doc: Document, error: str) -> None:
    doc.check_status, doc.check_error = Document.CheckStatus.FAILED, error
    doc.save(update_fields=["check_status", "check_error"])


def start_document_check(doc: Document) -> None:
    """Send the document to the API. Returns in under a second; the check runs in the background."""
    try:
        job = submit_check(doc.file, heatmap=True)
    except DocCheckerError as exc:
        return mark_failed(doc, f"{exc.code}: {exc}")
    doc.check_id, doc.check_status = job["check_id"], Document.CheckStatus.PENDING
    doc.save(update_fields=["check_id", "check_status"])
    if job["status"] == "done":          # the API already knew this file
        save_result(doc, job["result"])


def refresh_document_check(doc: Document) -> None:
    """If the check is still pending, ask the API whether it has finished."""
    if doc.check_status != Document.CheckStatus.PENDING or not doc.check_id:
        return
    try:
        job = get_check(doc.check_id)
    except DocCheckerError as exc:
        if exc.code == "check_not_found":   # the API restarted or the result expired: send it again
            return start_document_check(doc)
        return                              # API unreachable for now: try again on the next view
    if job["status"] == "done":
        save_result(doc, job["result"])
    elif job["status"] == "failed":
        mark_failed(doc, f"{job['error']['code']}: {job['error']['message']}")


def run_document_check(document_id: int) -> None:
    """Check and wait. Use this from a task queue such as Celery instead of start/refresh."""
    doc = Document.objects.get(pk=document_id)
    try:
        save_result(doc, check_document(doc.file, heatmap=True))
    except DocCheckerError as exc:
        mark_failed(doc, f"{exc.code}: {exc}")
```

### 3.4 Start the check after an upload (`views.py`)

```python
from django import forms
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from .models import Document
from .services import refresh_document_check, start_document_check


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["file"]


def upload_document(request):
    form = DocumentForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        doc = form.save()
        transaction.on_commit(lambda: start_document_check(doc))   # returns at once
        return redirect("document_detail", pk=doc.pk)
    return render(request, "documents/upload.html", {"form": form})


def document_detail(request, pk):
    doc = get_object_or_404(Document, pk=pk)
    refresh_document_check(doc)          # collects the result if it's ready
    return render(request, "documents/detail.html", {"doc": doc})
```

`urls.py`:

```python
from django.urls import path
from . import views

urlpatterns = [
    path("documents/upload/", views.upload_document, name="upload_document"),
    path("documents/<int:pk>/", views.document_detail, name="document_detail"),
]
```

### 3.5 Show the result (`templates/documents/detail.html`)

```html
<h2>Document check</h2>
{% if doc.check_status == "pending" %}
  <meta http-equiv="refresh" content="5">
  <p>⏳ The check is running. This page refreshes by itself.</p>
{% elif doc.check_status == "failed" %}
  <p>⚠ The automatic check could not run. Please review this document by hand.</p>
{% else %}
  {% with r=doc.check_result %}
  <p><strong>{{ doc.get_check_action_display }}</strong> ({{ doc.check_level }} level): {{ doc.check_message }}</p>
  <ul>
    {% for reason in r.reasons %}<li>{{ reason }}</li>{% endfor %}
  </ul>
  {% if r.action == "request_rescan" %}<p>Tell the applicant: {{ r.quality.advice }}</p>{% endif %}
  {% if r.page_count > 1 %}
    <table>
      <tr><th>Page</th><th>Result</th><th>Picture quality</th></tr>
      {% for p in r.pages %}
        <tr><td>{{ p.page }}</td><td>{{ p.message }}</td><td>{{ p.quality.category }}</td></tr>
      {% endfor %}
    </table>
  {% endif %}
  {% if doc.check_heatmap %}
    <img src="{{ doc.check_heatmap.url }}" alt="Colour map of page {{ r.worst_page }}: red areas may have been changed" width="500">
  {% endif %}
  <p><small>{{ r.note }} Check {{ r.check_id }}, {{ r.checked_at }}.</small></p>
  {% endwith %}
{% endif %}
```

### 3.6 A reviewer queue in the Django admin (`admin.py`)

```python
from django.contrib import admin
from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["id", "uploaded_at", "check_status", "check_action", "check_level", "check_message"]
    list_filter = ["check_status", "check_action", "check_level"]
    readonly_fields = ["check_id", "check_status", "check_action", "check_level", "check_message",
                       "check_result", "check_heatmap", "check_error", "checked_at"]
```

Filtering on **Check action = Send for manual review** gives reviewers their
queue. Filter on **Check level = high** to see the strongest cases first.

### With a task queue (optional)

If your project already uses **Celery**, you can run the waiting version in a
task instead of using start/refresh:

```python
# tasks.py
from celery import shared_task
from .services import run_document_check


@shared_task
def check_document_task(document_id: int) -> None:
    run_document_check(document_id)
```

In the upload view, use
`transaction.on_commit(lambda: check_document_task.delay(doc.pk))` instead
of `start_document_check`.

Both ways record API errors as `check_status = "failed"`, so a failed check
never blocks an application. Treat failed checks as "review by hand".

---

## 4. Good practice

- **Audit:** keep `check_id`, `checked_at`, `file.sha256`, `model.sha256` and
  `change.warning_level` with each decision (they're all in `check_result`).
  Then you can later show exactly which file, model and level produced it.
- **Privacy:** documents and heat maps are sensitive (medical and disability
  information). Serve `MEDIA` files only to authorised staff, set a retention
  period, and use HTTPS between Django and the API if they're on different
  machines. The API keeps files and results only in memory, and only for
  6 hours.
- **Monitoring:** poll `GET /health`, and keep track of the share of
  `manual_review` and `high` results. A sudden change usually means incoming
  documents look different from the training data.
- **Limits:** the model catches only some kinds of edits (about 28% of edited
  pages in its test), and it learned from computer-made edits. `continue` does
  **not** prove a document is genuine.
