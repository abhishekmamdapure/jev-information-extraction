import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend import store as _store
from backend.main import app

client = TestClient(app)

ITEMS = [dict(id=1, page=1, text='Total 100'), dict(id=2, page=2, text='Second page')]
TINY_PDF = b'%PDF-1.4\n%mock\n'


@pytest.fixture(autouse=True)
def _reset_store():
    # The document store is process-global and keyed by content hash; since
    # several tests below upload byte-identical TINY_PDF payloads, a cache
    # hit from an earlier test would short-circuit a later test's mocks.
    # Clear it before every test in this module so each one starts isolated.
    with _store._store_lock:
        _store._documents.clear()
    yield


def _patched():
    return patch('backend.main.inspect_pdf', return_value={'items': ITEMS, 'turns': {}})


@patch('backend.main.pdfium.PdfDocument')
def test_upload_document_returns_id_and_page_count(mock_pdfium):
    mock_pdfium.return_value.__enter__.return_value = [object(), object()]
    with _patched():
        response = client.post('/api/documents', files={'file': ('sample.pdf', TINY_PDF, 'application/pdf')})
    assert response.status_code == 200
    body = response.json()
    assert body['page_count'] == 2
    assert len(body['document_id']) == 64  # sha256 hex digest


def test_upload_document_rejects_oversized_file():
    oversized = b'0' * (20 * 1024 * 1024 + 1)
    response = client.post('/api/documents', files={'file': ('big.pdf', oversized, 'application/pdf')})
    assert response.status_code == 400
    assert '20 MB' in response.json()['detail']


@patch('backend.main.pdfium.PdfDocument', side_effect=ValueError('bad pdf'))
def test_upload_document_rejects_unreadable_pdf(mock_pdfium):
    response = client.post('/api/documents', files={'file': ('bad.pdf', TINY_PDF, 'application/pdf')})
    assert response.status_code == 400
    assert 'Could not read this PDF' in response.json()['detail']


def test_list_samples_returns_names():
    response = client.get('/api/samples')
    assert response.status_code == 200
    assert isinstance(response.json()['samples'], list)


def test_upload_sample_unknown_name_is_404():
    response = client.post('/api/documents/from-sample', json={'name': 'does-not-exist'})
    assert response.status_code == 404


def test_get_sample_questions_returns_nonempty_text():
    response = client.get('/api/sample-questions')
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body['text'], str)
    assert body['text'].strip() != ''
