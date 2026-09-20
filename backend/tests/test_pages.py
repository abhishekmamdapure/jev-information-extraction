# backend/tests/test_pages.py
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from backend import store
from backend.main import app

client = TestClient(app)


def _seed_document():
    items = [dict(id=1, page=1, text='Alpha'), dict(id=2, page=1, text='Beta'), dict(id=3, page=2, text='Gamma')]
    store.put('doc-1', data=b'%PDF', items=items, turns={1: 0, 2: 0}, page_count=2)
    return items


def test_get_page_items_filters_by_page():
    _seed_document()
    response = client.get('/api/documents/doc-1/pages/1/items')
    assert response.status_code == 200
    body = response.json()
    assert [i['id'] for i in body['items']] == [1, 2]
    assert body['text'] == 'Alpha\nBeta'


def test_get_page_items_out_of_range_is_404():
    _seed_document()
    response = client.get('/api/documents/doc-1/pages/99/items')
    assert response.status_code == 404


def test_get_page_items_unknown_document_is_404():
    response = client.get('/api/documents/does-not-exist/pages/1/items')
    assert response.status_code == 404


@patch('backend.main.render_page', return_value=(Image.new('RGB', (10, 20)), []))
def test_render_page_returns_png_with_size_headers(mock_render):
    _seed_document()
    response = client.get('/api/documents/doc-1/pages/1/render?scale=1.5&highlight=1')
    assert response.status_code == 200
    assert response.headers['content-type'] == 'image/png'
    assert response.headers['x-image-width'] == '10'
    assert response.headers['x-image-height'] == '20'
    passed_items = mock_render.call_args.args[2]
    assert [i['id'] for i in passed_items] == [1]


def test_render_page_malformed_highlight_is_400():
    _seed_document()
    response = client.get('/api/documents/doc-1/pages/1/render?highlight=abc')
    assert response.status_code == 400
