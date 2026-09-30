import hashlib
import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from time import perf_counter

import httpx
import pypdfium2 as pdfium
from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typesafe_sdk import Choice, TypeSafeClient

from backend import store
from backend.inspector import build_ocr_items, inspect_pdf, render_page, unrotated_page_size
from backend.schemas import EvaluateRequest, SampleRequest, UploadResponse

logger = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / 'frontend'
MAX_BYTES = 20 * 1024 * 1024
SAMPLE_DIR = Path(__file__).resolve().parent.parent / 'sample_pdf'
SAMPLE_QUESTIONS_FILE = Path(__file__).resolve().parent.parent / 'sample_questions.txt'
ATOM_URL = 'https://at0m.pienomial.com/decide/v0'

app = FastAPI(title='PDF Inspector API')
allowed_origins = [origin.strip() for origin in os.environ.get('FRONTEND_ORIGINS', '').split(',') if origin.strip()]
if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=['GET', 'POST'],
        allow_headers=['Content-Type'],
        expose_headers=['X-Image-Width', 'X-Image-Height'],
    )


@app.get('/api/health')
def health():
    return {'status': 'ok'}


def _ingest(data: bytes) -> dict:
    if len(data) > MAX_BYTES:
        raise HTTPException(400, 'Please use a PDF smaller than 20 MB.')
    document_id = hashlib.sha256(data).hexdigest()
    cached = store.get(document_id)
    if cached is not None:
        return {'document_id': document_id, 'page_count': cached['page_count']}
    try:
        with pdfium.PdfDocument(data) as doc:
            page_count = len(doc)
        if not 1 <= page_count <= 200:
            raise ValueError('Please use a PDF with 1-200 pages for this demo.')
        result = inspect_pdf(data)
    except Exception as exc:
        raise HTTPException(400, f'Could not read this PDF: {exc}')
    pages_with_text = {item['page'] for item in result['items']}
    next_id = len(result['items']) + 1
    for page_number in range(1, page_count + 1):
        if page_number in pages_with_text:
            continue
        try:
            page_size = unrotated_page_size(data, page_number - 1)
            ocr_items = build_ocr_items(data, page_number, page_size, next_id)
        except Exception as exc:
            logger.warning('OCR failed for %s page %s: %s', document_id, page_number, exc)
            continue
        result['items'].extend(ocr_items)
        next_id += len(ocr_items)
    store.put(document_id, data=data, items=result['items'], turns=result['turns'], page_count=page_count)
    return {'document_id': document_id, 'page_count': page_count}


@app.post('/api/documents', response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    return _ingest(await file.read())


@app.get('/api/samples')
def list_samples():
    return {'samples': [p.stem.replace('-', ' ') for p in sorted(SAMPLE_DIR.glob('*.pdf'))]}


@app.post('/api/documents/from-sample', response_model=UploadResponse)
def upload_sample(body: SampleRequest):
    matches = [p for p in sorted(SAMPLE_DIR.glob('*.pdf')) if p.stem.replace('-', ' ') == body.name]
    if not matches:
        raise HTTPException(404, 'Sample not found.')
    return _ingest(matches[0].read_bytes())


def _get_document(document_id: str) -> dict:
    document = store.get(document_id)
    if document is None:
        raise HTTPException(404, 'Document not found. Upload it again.')
    return document


def _page_items(document: dict, page_number: int) -> list:
    if not 1 <= page_number <= document['page_count']:
        raise HTTPException(404, f"Page {page_number} is out of range (1-{document['page_count']}).")
    return [i for i in document['items'] if i['page'] == page_number]


@app.get('/api/documents/{document_id}/pages/{page_number}/items')
def get_page_items(document_id: str, page_number: int):
    document = _get_document(document_id)
    items = _page_items(document, page_number)
    return {'items': items, 'text': '\n'.join(i['text'] for i in items)}


@app.get('/api/documents/{document_id}/pages/{page_number}/render')
def render_page_endpoint(document_id: str, page_number: int, scale: float = 1.5, highlight: str = ''):
    document = _get_document(document_id)
    items = _page_items(document, page_number)
    try:
        highlight_ids = {int(x) for x in highlight.split(',') if x.strip()}
    except ValueError:
        raise HTTPException(400, 'Invalid highlight ids.')
    visible = [i for i in items if i['id'] in highlight_ids]
    with store.render_lock:
        image, _rows = render_page(document['data'], page_number - 1, visible,
                                    document['turns'].get(page_number), True, None, scale)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return Response(content=buffer.getvalue(), media_type='image/png',
                     headers={'X-Image-Width': str(image.width), 'X-Image-Height': str(image.height)})


def _build_questions(items: list, questions: list) -> dict:
    return {f'q{index}': Choice(instructions=question,
                                 criteria={str(i): item['text'] for i, item in enumerate(items)})
            for index, question in enumerate(questions, 1)}


def _resolve_api_key(raw_key: str) -> str:
    return raw_key.strip()


def _open_client(model: str, api_key: str):
    # ATOM is a public endpoint and needs no key; Jev goes through the TypeSafe SDK.
    return httpx.Client(timeout=60) if model == 'atom' else TypeSafeClient(api_key=api_key)


def _decide(client, model: str, items: list, questions: list) -> dict:
    text = '\n'.join(i['text'] for i in items)
    if model == 'atom':
        # Each extracted item is one choice option; ATOM returns a probability per option.
        criteria = {str(i): item['text'] for i, item in enumerate(items)}
        payload = {'state': text, 'questions': {
            f'q{index}': {'type': 'choice', 'instructions': question, 'criteria': criteria}
            for index, question in enumerate(questions, 1)}}
        response = client.post(ATOM_URL, json=payload)
        response.raise_for_status()
        answers = response.json()['answers']
        return {'answers': {name: {'probabilities': a['probs']} for name, a in answers.items()},
                'usage': None, 'model': 'at0m-v0'}
    response = client.system_one(state=text, questions=_build_questions(items, questions), model='jev-latest')
    return {
        'answers': {name: {'probabilities': a.probabilities} for name, a in response.answers.items()},
        'usage': {'input_tokens': response.usage.input_tokens, 'output_tokens': response.usage.output_tokens},
        'model': response.model,
    }


@app.post('/api/documents/{document_id}/pages/{page_number}/evaluate')
def evaluate_page(document_id: str, page_number: int, body: EvaluateRequest):
    document = _get_document(document_id)
    items = _page_items(document, page_number)
    questions = [q.strip() for q in body.questions if q.strip()]
    api_key = _resolve_api_key(body.api_key)
    if body.model == 'jev' and not api_key:
        raise HTTPException(400, 'Enter your TypeSafe API key in Session access.')
    if not items:
        raise HTTPException(400, 'This page has no readable text, even after OCR.')
    if not questions:
        raise HTTPException(400, 'Add at least one question.')
    started = perf_counter()
    try:
        with _open_client(body.model, api_key) as client:
            result = _decide(client, body.model, items, questions)
    except Exception as exc:
        detail = str(exc).replace(api_key, '[redacted]') if api_key else str(exc)
        raise HTTPException(502, f'Evaluation failed ({type(exc).__name__}): {detail or "Unknown SDK error."}')
    return {**result, 'eval_seconds': perf_counter() - started}


@app.post('/api/documents/{document_id}/evaluate-batch')
def evaluate_batch(document_id: str, body: EvaluateRequest):
    document = _get_document(document_id)
    questions = [q.strip() for q in body.questions if q.strip()]
    api_key = _resolve_api_key(body.api_key)
    if body.model == 'jev' and not api_key:
        raise HTTPException(400, 'Enter your TypeSafe API key in Session access.')
    if not questions:
        raise HTTPException(400, 'Add at least one question.')
    page_count = min(body.page_limit or document['page_count'], document['page_count'])
    pages = list(range(1, page_count + 1))
    items_by_page = {p: [i for i in document['items'] if i['page'] == p] for p in pages}

    def process_page(client, p):
        page_items = items_by_page[p]
        if not page_items:
            return p, {'skipped': True, 'reason': 'No readable text, even after OCR'}
        render_started = perf_counter()
        with store.render_lock:
            render_page(document['data'], p - 1, page_items, document['turns'].get(p), True, None, 1.5)
        render_seconds = perf_counter() - render_started
        try:
            eval_started = perf_counter()
            result = _decide(client, body.model, page_items, questions)
            return p, {**result, 'eval_seconds': perf_counter() - eval_started, 'render_seconds': render_seconds}
        except Exception as exc:
            detail = str(exc).replace(api_key, '[redacted]') if api_key else str(exc)
            return p, {'error': detail, 'render_seconds': render_seconds}

    batch_started = perf_counter()
    page_stats = {}
    try:
        with _open_client(body.model, api_key) as client:
            with ThreadPoolExecutor(max_workers=min(8, len(pages))) as pool:
                futures = [pool.submit(process_page, client, p) for p in pages]
                for future in as_completed(futures):
                    p, outcome = future.result()
                    page_stats[p] = outcome
    except Exception as exc:
        detail = str(exc).replace(api_key, '[redacted]') if api_key else str(exc)
        raise HTTPException(502, f'Batch evaluation failed ({type(exc).__name__}): {detail or "Unknown SDK error."}')
    return {'page_count': len(pages), 'total_seconds': perf_counter() - batch_started, 'page_stats': page_stats}


@app.get('/api/sample-questions')
def get_sample_questions():
    text = SAMPLE_QUESTIONS_FILE.read_text(encoding='utf-8-sig')
    questions = ' <> '.join(q.strip() for q in text.replace('<>', '\n').splitlines() if q.strip())
    return {'text': questions}


# Keep this mount as the LAST statement in the file — every API route above
# must be registered before the catch-all static mount (see Global Constraints).
app.mount('/', StaticFiles(directory=FRONTEND_DIR, html=True), name='frontend')
