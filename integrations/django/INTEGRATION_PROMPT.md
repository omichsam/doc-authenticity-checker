# Prompt: integrate the document checker into a Django project

Copy everything below the line into an AI coding assistant opened in your
Django project. Attach or paste `doc_checker.py` (from this folder) with it.
Fill in the two `<…>` placeholders first.

---

You are working in my Django project. Integrate an existing **document
authenticity checker** so that every uploaded applicant document is checked
automatically, and staff can see the result and a reviewer queue.

## Context: the checker API (already built and running; do not change it)

- It's a separate HTTP service at `<DOC_CHECKER_URL, e.g. http://127.0.0.1:8100>`.
  Every `/v1/...` call needs the header `X-API-Key: <key>`.
- `POST /v1/checks` with `multipart/form-data`, field **`file`**, starts a
  **background check**.
  - It accepts an image (PNG/JPG/WEBP/TIFF/BMP) or a PDF of up to 20 pages,
    up to 25 MB. Add `?heatmap=true` to also get a PNG colour map.
  - It returns **202** at once with `{"check_id", "status", "status_url", ...}`.
  - If the same file was checked recently, `status` is already `"done"` and
    `result` is included.
- `GET /v1/checks/{check_id}` returns `status` `queued` | `running` | `done`
  (with `result`) | `failed` (with `error`).
  - Results are kept only 6 hours and are lost when the API restarts. A **404
    `check_not_found`** means: submit the file again.
- `POST /v1/check` (no "s") does the same but waits for the result, which
  takes 5–20 s per page on a CPU. Use it only from a task queue.
- Errors always look like `{"error": {"code": "...", "message": "..."}}`:
  - 400: `missing_file`, `empty_file`
  - 401: `invalid_api_key`
  - 404: `check_not_found`
  - 413: `file_too_large`, `too_many_pages`
  - 415: `unsupported_file`, `encrypted_pdf`
  - 503: `busy`
- `result` fields to use:
  - **`action`**: `continue` | `manual_review` | `request_rescan`. **This is
    what the system acts on.**
  - **`level`**: `low` | `medium` | `high`. For sorting the review queue.
  - **`message`**: one plain sentence for staff.
  - **`reasons`**: a list of plain sentences explaining the action.
  - `quality.score` (0–100), `quality.category` (`GOOD` | `ACCEPTABLE` |
    `POOR`), `quality.advice`: text to tell the applicant when `action` is
    `request_rescan`.
  - `change.score`, `change.warning_level`, `change.compared_to_real_pages`,
    `change.regions` (boxes in pixels and in `*_pct` of the page).
  - `page_count`, `worst_page`, `pages[]` (one result per PDF page; the
    document takes its worst page's result).
  - `check_id`, `checked_at`, `file.sha256`, `model.sha256`: keep these for
    audit.
  - `heatmap_png_base64`: only with `?heatmap=true`. It's large, so **never
    store it in the database**.
- A ready-made client is attached: **`doc_checker.py`**. It provides
  `submit_check(file, heatmap=False)`, `get_check(check_id)`,
  `check_document(file, heatmap=False)` (waits), `heatmap_bytes(result)` and
  `DocCheckerError` (with `.code` and `.status`). It reads `DOC_CHECKER_URL`,
  `DOC_CHECKER_API_KEY` and `DOC_CHECKER_TIMEOUT` from Django settings.
  **Use it as it is**; don't write a new HTTP client.

## What to do

1. **Explore first.** Find where applicant documents are uploaded and stored:
   the model with the `FileField`/`ImageField`, its form or serializer, its
   views, and the admin. Tell me what you found and your plan **before**
   changing anything. If documents are stored in more than one model, or
   there is no file model, ask me.
2. **Add the client.**
   - Put `doc_checker.py` in the app that owns the document model.
   - Add `requests` to the project's requirements if it's missing.
   - In `settings.py`, read `DOC_CHECKER_URL` (default
     `http://127.0.0.1:8100`) and `DOC_CHECKER_API_KEY` **from environment
     variables**, and add `DOC_CHECKER_TIMEOUT = 120`.
   - Never hard-code the key or commit it.
3. **Store the result on the existing document model.** Don't create a
   parallel model unless I agree. Add these fields with a migration:
   - `check_id` (CharField 40, blank)
   - `check_status`: TextChoices `pending` / `done` / `failed`, default
     `pending`
   - `check_action`: TextChoices `continue` / `manual_review` /
     `request_rescan`, blank, with readable labels "No action needed" /
     "Send for manual review" / "Ask for a clearer scan"
   - `check_level` (CharField 10, blank)
   - `check_message` (CharField 255, blank)
   - `check_result` (JSONField, null)
   - `check_heatmap` (FileField, blank)
   - `check_error` (TextField, blank)
   - `checked_at` (DateTimeField, null)

   Existing rows must stay valid after the migration.
4. **Write a `services.py`** with these functions:
   - `start_document_check(doc)`: call `submit_check(doc.file, heatmap=True)`
     and save `check_id` and status `pending`. If the response is already
     `done`, save the result straight away.
   - `refresh_document_check(doc)`: only when pending. Call `get_check`.
     - On `done`: save the result.
     - On `failed`: mark the check failed.
     - On `DocCheckerError` with code `check_not_found`: start the check
       again.
     - On any other `DocCheckerError`: leave it pending, to be tried on the
       next view.
   - `save_result(doc, result)`:
     - Decode the heat map with `heatmap_bytes` and save it to
       `check_heatmap`.
     - Remove `heatmap_png_base64` from the result, and from every `pages[]`
       entry, before storing it in `check_result`.
     - Fill in `check_action`, `check_level`, `check_message` and
       `checked_at`.
   - `mark_failed(doc, error)`.
5. **Hook it into the upload flow.**
   - After a document is saved (in every place that creates documents, such
     as the form view, the API view or the admin), call
     `transaction.on_commit(lambda: start_document_check(doc))`.
   - The upload must **not** wait for the check, and must never fail
     because the checker is down.
   - If the project already uses Celery, ask me whether to use a task with
     `check_document()` instead.
6. **Show the result to staff.** On the document's detail page, call
   `refresh_document_check(doc)` before rendering, then show:
   - While pending: "Check running…", and refresh the page every 5 seconds.
   - When failed: "The automatic check could not run — please review this
     document by hand."
   - When done:
     - the action label and the `level`, then the `message` and the list of
       `reasons`;
     - the heat map image;
     - for a PDF, a table with one row per page (`page`, `message`,
       `quality.category`);
     - the `note` disclaimer, with `check_id` and `checked_at`.
   - Only when `action == "request_rescan"`: "Tell the applicant:" followed
     by `quality.advice`.
   - Use the project's existing templates and style.
7. **Build the reviewer queue in the admin.**
   - Show `check_status`, `check_action`, `check_level` and `check_message`
     in the list.
   - Add filters on `check_status`, `check_action` and `check_level`.
   - Make all `check_*` fields read-only.
8. **Write tests** that never call the real API: patch `submit_check`,
   `get_check` and `check_document`. Cover:
   - an upload starts a check and the upload request does not wait;
   - a pending result turns into done;
   - `failed`;
   - `check_not_found` leads to a resubmit;
   - the API being unreachable leaves the document pending and the upload
     still succeeds;
   - the heat map is saved as a file and not inside `check_result`;
   - the admin filters work.
9. **Finish by running** the migrations and the full test suite. Report what
   you changed, file by file, and anything you weren't sure about.

## Rules you must follow

- **The result routes documents; it never decides them.**
  - Never reject, delete or block an application automatically because of
    `action` or `level`.
  - `manual_review` means "a person looks at it".
  - `request_rescan` means "ask the applicant for a clearer picture".
- A missing or failed check must lead to **review by hand**, never to
  silently approving or rejecting the document.
- These are sensitive medical and disability documents:
  - Show results and heat maps only to authorised staff, using the project's
    existing permissions.
  - Never log file contents, heat maps or full results. Logging `check_id`
    is fine.
- Don't change the checker API or `doc_checker.py`. If something seems to
  need a change there, tell me instead.
- Keep to the project's existing code style, and don't refactor unrelated
  code.
