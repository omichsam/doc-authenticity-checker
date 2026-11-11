# Sample files for the Postman collection

The collection uploads these files. Three are included:

- `damaged.pdf`: a broken PDF; the API must reply 415.
- `empty.jpg`: an empty file; the API must reply 400.
- `not-an-image.txt`: a text file; the API must reply 415.

The page images come from the ClinOCR-Bench dataset, so they aren't included
in the repository. Add your own files with these names before running the
collection:

| File | What it should be | The collection expects |
| --- | --- | --- |
| `genuine-page.jpg` | A clear scan of a real, unchanged form | `continue`, quality GOOD, level low |
| `blurry-page.jpg` | A blurry scan | `request_rescan`, quality POOR |
| `edited-page.jpg` | A form with one value changed near the top left | `manual_review`, level high |
| `background-page.jpg` | Any other page, not checked before in the run | finishes as a background check |
| `two-page-document.pdf` | A 2-page PDF: page 1 genuine, page 2 edited | page 2 decides, `manual_review` |

If you have the notebook's `data/` folder, you can recreate the exact files
used to test the API. The edited page is made with `make_forgery(..., "field_edit",
random.Random(7))` and `post_process(..., random.Random(8))` from
`tamper_core.py`, applied to
`data/clinocr/ClinOCR-Bench/scans/normal/template_1_sample_1_normal.jpg`.
