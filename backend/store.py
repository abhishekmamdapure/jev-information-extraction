"""In-memory document cache: extraction runs once per uploaded PDF, keyed by its SHA-256 hash.

PDFium's native library is not thread-safe even across independent
PdfDocument instances: render_lock serializes every render_page() call
across the whole process, mirroring app.py's original _render_lock.
"""
import threading

render_lock = threading.Lock()

_documents = {}
_store_lock = threading.Lock()


def put(document_id, data, items, turns, page_count):
    with _store_lock:
        _documents[document_id] = {
            'data': data, 'items': items, 'turns': turns, 'page_count': page_count,
        }


def get(document_id):
    with _store_lock:
        return _documents.get(document_id)
