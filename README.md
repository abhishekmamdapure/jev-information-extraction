# PDF Inspector — minimal local demo

A Python **FastAPI** backend with a static **Oat UI** frontend, using Firecrawl's **pdf-inspector 1.21.0** for all text extraction and positioning. PDFium renders the original page; Pillow draws the boxes. No Node.js, Rust build, API key, Poppler installation, or hosted service is required on supported wheel platforms.

## Run in VS Code on Windows

1. Install **64-bit Python 3.12** from https://www.python.org/downloads/ if needed. Include the Python launcher during installation.
2. Extract this ZIP. Open the inner `pdf-inspector-demo` folder in VS Code (the folder containing `backend/`, `frontend/`, and `requirements.txt`).
3. Choose **Terminal → New Terminal**. In PowerShell run these commands one at a time:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

4. Open http://127.0.0.1:8000/ if the browser does not open automatically.
5. Upload an invoice PDF. The right side displays the original PDF. Evaluate the page to show matching text and blue boxes.
6. Set the probability threshold in the sidebar to filter matching chunks, or navigate to another page and evaluate it.
7. Use the download buttons to save page text, the preview PNG, or JSON with text, original coordinates, font metadata, and rendered top-left boxes.
8. Press **Ctrl+C** in the terminal to stop the app.

Virtual-environment activation is unnecessary with these commands, so PowerShell execution-policy changes are unnecessary. If `py -3.12` fails, install Python 3.12 or use the full path to its `python.exe`. Avoid installing these requirements into an unrelated application environment.

Optional VS Code debugging: install Microsoft's Python and Python Debugger extensions; use **Python: Select Interpreter** to select `.venv`; then press **F5** and select **PDF Inspector UI**. The included launch configuration starts uvicorn with `--reload`.

## macOS / Linux

Use Python 3.12:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --only-binary=:all: -r requirements.txt
.venv/bin/python -m uvicorn backend.main:app --reload
```

If port 8000 is occupied, append `--port 8001` to the run command and open http://127.0.0.1:8001/. Run from this project folder so relative paths (frontend static files, sample PDFs) resolve correctly.

## Files

- `backend/main.py`: FastAPI app — document upload/sample endpoints, page item and PNG render endpoints, single-page and batch evaluate endpoints, and the static-file mount that serves `frontend/`.
- `backend/inspector.py`: native extraction, coordinate transforms, PDF rendering and overlay drawing (canonical copy; the former root-level `inspector.py` was retired).
- `backend/store.py`: in-memory per-document store.
- `backend/schemas.py`: request/response models.
- `backend/tests/`: pytest suite covering documents, pages, evaluate, evaluate-batch, store, and health endpoints.
- `frontend/`: static Oat UI (`index.html`, `app.js`, `styles.css`) — sidebar source picker, PDF preview, page navigation, threshold slider, and the batch-evaluation timing table.
- `requirements.txt`: pinned direct dependencies.
- `.vscode/launch.json`: optional VS Code debugger configuration (launches uvicorn).

## Coordinate conversion

For an ordinary unrotated page, with visible page height H:

```python
bbox = [x, H - y - height, x + width, H - y]
```

These are top-left-origin **PDF points**, not pixels. One point is 1/72 inch. `render_page` scales X and Y separately using the actual raster dimensions before drawing. For cropped pages, the extractor already expresses coordinates relative to the visible CropBox/MediaBox intersection: do not subtract the crop origin a second time.

The extractor can rebase predominantly rotated text into a synthetic frame. The demo calls `extract_text_with_positions_and_rotations_bytes`, reverses that rebase, applies the PDF page's `/Rotate`, and finally flips Y. The original PDF is not modified on disk. JSON includes both the original item coordinates and `bbox_top_left_pt` for the displayed page.

**These are text-run font-metric boxes, not precise glyph outlines.** For horizontal text the box extends upward from the baseline by the reported height; descenders may fall below it. Unknown font advances may be estimated (`advance_known=false`). A returned item may contain a word, multiple words, or a line; the app draws one box per returned text item, not per character or semantic invoice field.

## Scope

### TypeSafe invoice extraction

Use the header's **API key** button to enter your session key. Before uploading
or choosing a sample, select **All pages** or **First N pages** (1-200).
Local inspection reads the document to establish its page count; the selection
limits evaluation, not local text extraction. Counts above the document length
are capped to the available pages. Uploading does not call TypeSafe.
Edit the questions, then select **Run evaluation** to process the chosen pages.

Questions and answers appear beside the PDF, for the page selected in the toolbar.
The strongest match is shown first; expand **Alternative match** for the runner-up.
Probability meters use green for 80% and above, amber for 50% to below 80%, and
red below 50%, with numeric and text labels. These are match probabilities.

The **Minimum chunk probability** number field (default 0.9, range 0-1) controls which matches receive padded
red outlines on the PDF. Changing it reuses existing results. Extracted text and
per-page timings are available in expandable sections. Pages outside the selected
scope remain available for inspection and are labeled as not evaluated.

The key stays only in the browser's in-memory form field until refresh, navigation,
tab closure, or **Clear key**. No browser storage or server environment key is used.
It is sent directly in
the evaluate request body to a request-scoped SDK client on the backend. It is not
written to files, environment variables, URLs, caches, or application logs. PDF
text extraction is local; evaluation sends current-page text and questions to
TypeSafe.

Run the backend test suite with `python -m pytest backend/tests`.

### PDF inspector

- Embedded text extraction only; OCR models are not loaded or downloaded. A scan without an existing text layer shows its page image and an explanatory message.
- PDF inspection itself makes no LLM calls. The evaluation action uses TypeSafe.
- Up to 20 MB and 200 pages. Preview's longest side is capped at 3000 pixels. All positions are extracted once per uploaded document; only the current page is rendered.
- Current document metadata lives in the backend's in-memory store, keyed by document id, with no shared extraction cache across restarts. The app does not persist uploads to project files or send PDFs to a cloud service. Dependencies need internet access during installation.
- Password-protected documents are not supported. Malformed files surface a readable error.
- Intended as a local developer demo, not a public multi-user service.
- Text is shown in extractor item order, one region per line; it is not a reconstruction of a formatted invoice table. The text-area content is a display; downloads use the extracted original text.

## Verification performed

Tested with Python 3.12 on Linux and the exact direct dependency versions in requirements.txt:

- Native pdf-inspector extraction and PDFium rendering of synthetic invoice text.
- Cropped pages with /Rotate values 0, 90, 180 and 270; computed boxes intersect the rendered text.
- Dominant vertical text in both directions, including extractor frame rebasing.
- Visual inspection of a rotated-page overlay.
- Backend pytest suite (`backend/tests`): document upload and sample selection, page items and rendering, single-page and batch evaluation (including missing-key and empty-page cases), and the in-memory store.

Windows setup commands are provided but were not executed on Windows in this environment. An actual user invoice has not been tested.

## Upstream references

- Repository: https://github.com/firecrawl/pdf-inspector
- Python API: https://github.com/firecrawl/pdf-inspector/blob/main/docs/python.md
- Bounding-box semantics: https://github.com/firecrawl/pdf-inspector/blob/main/src/types.rs
- Frame conversion: https://github.com/firecrawl/pdf-inspector/blob/main/src/extractor/display_frame.rs
- Dominant text rotation: https://github.com/firecrawl/pdf-inspector/blob/main/src/extractor/geometry.rs

Firecrawl pdf-inspector is MIT licensed. This demo consumes its published package and does not bundle its source or native binary. Other installed dependencies retain their respective licenses.
