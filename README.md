# Jev Information Extraction

Ask questions about a PDF. Use Jev to rank the source text that answers them. Inspect each match, its probability, and its location on the original page.

This interactive demo uses **TypeSafe's `jev-latest` model** through the Python SDK's `system_one` API. It turns extracted PDF text into candidate answers for natural-language questions such as ?What is the GST number?? or ?What is the total invoice amount??. A FastAPI service runs the evaluation and serves the Oat UI frontend from one URL.

## How Jev is used

1. **Read the PDF:** `pdf-inspector` extracts embedded text chunks and their positions. PDFium renders the page. This step does not call Jev.
2. **Create candidate answers:** for each question, the backend creates a TypeSafe `Choice`. Its instructions contain the question; its criteria map page-local chunk indexes to the extracted text.
3. **Evaluate with Jev:** the backend sends the page text and all questions for that page to `client.system_one(..., model='jev-latest')`.
4. **Rank the results:** returned probabilities are mapped back to the original chunks. The UI shows the highest-scoring chunk and an expandable second-best match.
5. **Inspect the evidence:** red boxes mark qualifying chunks on the PDF. Zoom and page navigation let you check the source beside the answers.

The core call follows this pattern:

```python
from typesafe_sdk import Choice, TypeSafeClient

questions = {
    'q1': Choice(
        instructions='What is the total invoice amount?',
        criteria={str(i): item['text'] for i, item in enumerate(page_items)},
    )
}

with TypeSafeClient(api_key=session_key) as client:
    response = client.system_one(
        state='\n'.join(item['text'] for item in page_items),
        questions=questions,
        model='jev-latest',
    )
```

`page_items` comes from PDF extraction; `session_key` comes from the frontend. See `backend/main.py` for the complete implementation.

## What ?evaluation? means here

This is **question-to-text-chunk selection**, performed independently for each selected page. It is not a ground-truth benchmark, and the app does not calculate accuracy, precision, recall, or F1. A displayed probability is the model's score for a candidate, not a measured guarantee that the answer is correct.

| UI result | Meaning |
| --- | --- |
| Primary answer | Highest-probability source chunk for that question on the current page |
| Alternative match | Second-highest-probability chunk, when available |
| Green meter | Probability at least 80% |
| Amber meter | Probability at least 50% and below 80% |
| Red meter | Probability below 50% |
| Minimum chunk probability | Highlight cutoff, default `0.9`; does not change the model request or hide ranked answers |

A chunk is highlighted if it meets the cutoff for **any** question. The app displays source text as extracted; it does not combine chunks into a rewritten answer or normalize values. For example, asking for ?only the number? does not guarantee removal of a currency label present in the matched chunk.

**Run evaluation** processes all pages or the first N pages, with up to eight page tasks in parallel. Each nonempty page gets its own Jev request containing all questions. Pages without embedded text are skipped. Results remain page-specific; there is no cross-page answer aggregation.

The UI shows total batch wall time and current-page render/evaluation timings. The batch render timing includes any wait for the rendering lock; it is not the duration of every subsequent preview refresh. The API also returns the resolved model name and token usage for successful page evaluations.

## Run locally

### Requirements

- Git and 64-bit Python 3.12.
- A TypeSafe API key with access to `jev-latest` for evaluation.
- Internet access to install dependencies, load Oat UI assets, and call TypeSafe.

PDF upload, extraction, and preview work without an API key. Node.js is not required.

### 1. Clone the project

```bash
git clone https://github.com/abhishekmamdapure/jev-information-extraction.git
cd jev-information-extraction
```

Run all following commands from this directory.

### 2. Install and start ? Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

### 2. Install and start ? macOS / Linux

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --only-binary=:all: -r requirements.txt
.venv/bin/python -m uvicorn backend.main:app --reload
```

### 3. Open the app

Visit **http://127.0.0.1:8000/**. Keep the terminal running. Press **Ctrl+C** to stop the server.

If port 8000 is occupied, append `--port 8001` to the start command and open http://127.0.0.1:8001/ instead.

## Run your first Jev evaluation

1. Click **API key** at the top right and paste your TypeSafe key. The eye button toggles visibility.
2. Choose **All pages** or **First N pages** before uploading. N must be between 1 and 200. This limits model evaluation, not initial PDF extraction.
3. Upload a PDF or open one of the five invoice samples under **Samples**.
4. Enter one question per line. For example:

   ```text
   What is the GST number?
   What is the total invoice amount?
   What is the name of the seller?
   What is the name of the buyer?
   ```

5. Click **Run evaluation**. Uploading alone does not make a TypeSafe request.
6. Review the scrollable **Questions & answers** panel, probability meters, and alternative matches.
7. Inspect the red boxes in **Page preview**. Use Fit width, Fit page, or the zoom buttons. Change **Minimum chunk probability** to adjust highlights without rerunning Jev.
8. Use **Previous / Next** to inspect other pages. **View extracted text** opens the raw text with Copy and Close controls.

## Deploy the complete app on Railway

The frontend and API run as **one service**. The repository includes a Python 3.12 `Dockerfile`, `railway.json`, and the five sample PDFs.

1. In Railway, create a project and select **Deploy from GitHub repo**.
2. Connect this repository and select branch **main**.
3. Leave Root Directory blank or set it to `/`.
4. Let Railway use the root Dockerfile. Leave custom build and start commands blank: the Dockerfile installs dependencies and starts Uvicorn on Railway's `PORT`.
5. The checked-in configuration sets one replica, `/api/health` as the health check, a 120-second health-check timeout, and restart on failure. Keep one worker and one replica because documents are stored in process memory.
6. No app environment variables are required for this single-service setup. Do not add a TypeSafe key: users enter their own session key in the UI.
7. Apply any staged changes and deploy. Wait for a successful deployment.
8. Open **Settings ? Networking ? Generate Domain**. If prompted, select the port detected from the running service.
9. Visit `https://YOUR-DOMAIN/api/health`; expect `{"status":"ok"}`. Open `https://YOUR-DOMAIN/` to use the app.
10. Open a sample, enter a session key, and run an evaluation to verify the full flow.

GitHub Pages and a separate frontend host are not needed. See the [Railway FastAPI guide](https://docs.railway.com/guides/fastapi) and [Docker start-command documentation](https://docs.railway.com/deployments/start-command).

## Data handling and limits

- The browser keeps the API key in the page's in-memory field, not browser storage. Refreshing, leaving the page, or selecting Clear key removes it from the UI.
- Evaluation sends the key to the backend, which uses it in a request-scoped TypeSafe client. The app does not persist the key in files or environment variables.
- Uploaded PDFs are processed on the backend host. For evaluation, page text, questions, and candidate text are sent to TypeSafe; the model call does not send the PDF image.
- Documents and extracted data are retained in server process memory until restart. There is no user authentication, per-user document isolation, or automatic expiry. This is a demo, not a private multi-user document service.
- PDFs must be no larger than 20 MB and contain 1?200 pages. Password-protected PDFs are unsupported.
- Extraction uses existing embedded text. OCR is not enabled, so scanned pages without a text layer cannot be evaluated.
- Chunk boundaries affect answer quality: a value split across multiple chunks is not automatically combined. Boxes reflect extracted text regions, not semantic fields.
- Frontend preview rendering defaults to 2?, subject to a 3000-pixel longest-side cap. Display zoom is independent of rendering resolution.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Run evaluation is disabled | Load a document, add a key and at least one question, and check the page limit. |
| TypeSafe evaluation fails | Check the key's validity and model access; read the error displayed by the app. |
| No embedded text | Use a text-based PDF; scanned images require OCR outside this demo. |
| No red boxes | Run evaluation, enable Show bounding boxes, and check the highlight threshold. |
| Page was not evaluated | Expand the selected page scope and run evaluation again. |
| Document not found after deployment | The server restarted; upload the PDF again or reopen a sample. |
| Railway build or startup fails | Check the first error in deployment logs, the main branch, repository root, and Dockerfile detection. |

## Tests and code map

Install pytest into the same environment used above, then run the tests:

```powershell
# Windows
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

```bash
# macOS / Linux
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest backend/tests -q
```

The tests check API behavior, document processing, and mocked evaluation flows. They do not measure Jev's real-world answer accuracy.

| Path | Purpose |
| --- | --- |
| `backend/main.py` | Jev requests, candidate construction, page evaluation, API routes, frontend hosting |
| `backend/inspector.py` | PDF extraction, rendering, coordinate mapping, red boxes |
| `backend/store.py` | In-memory documents and rendering lock |
| `backend/schemas.py` | Request validation |
| `frontend/` | Oat UI, session key input, ranked answers, probability meters, PDF preview |
| `sample_pdf/` | Five demo invoices |
| `sample_questions.txt` | Default questions |
| `Dockerfile`, `railway.json` | Single-service Railway deployment |

PDF extraction uses [Firecrawl pdf-inspector](https://github.com/firecrawl/pdf-inspector), rendering uses PDFium, and overlays use Pillow. Jev performs the candidate evaluation through TypeSafe.
