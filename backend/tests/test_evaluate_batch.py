import os
import pytest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from backend import store
from backend.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _seed_document():
    items = [dict(id=1, page=1, text='Repeated'), dict(id=2, page=2, text='Total 100')]
    store.put('doc-batch', data=b'%PDF', items=items, turns={}, page_count=3)  # page 3 has no text


def _response():
    return SimpleNamespace(
        answers={'q1': SimpleNamespace(probabilities={'0': 0.9})},
        usage=SimpleNamespace(input_tokens=50, output_tokens=5), model='jev-latest')


@patch('backend.main.render_page', return_value=(Image.new('RGB', (5, 5)), []))
def test_batch_evaluate_covers_every_page(mock_render):
    _seed_document()
    with patch('backend.main.TypeSafeClient') as factory:
        factory.return_value.__enter__.return_value.system_one.return_value = _response()
        response = client.post('/api/documents/doc-batch/evaluate-batch',
                                json={'questions': ['Q?'], 'api_key': 'test-key'})
    assert response.status_code == 200
    body = response.json()
    assert body['page_count'] == 3
    stats = body['page_stats']
    assert set(stats) == {'1', '2', '3'}
    assert stats['3']['skipped'] is True
    assert stats['1']['model'] == 'jev-latest'
    assert stats['1']['request']['url'] == 'https://api.typesafe.ai/v1/systemone'
    assert stats['1']['request']['body'] == {'state': 'Repeated', 'model': 'jev-latest', 'questions': {
        'q1': {'type': 'choice', 'instructions': 'Q?', 'criteria': {'0': 'Repeated'}}}}
    assert 'test-key' not in str(stats['1']['request'])
    assert 'render_seconds' in stats['1']


def test_batch_evaluate_missing_api_key_is_400():
    _seed_document()
    with patch.dict(os.environ, {'TYPESAFE_API_KEY': 'server-key-must-not-be-used'}):
        response = client.post('/api/documents/doc-batch/evaluate-batch',
                                json={'questions': ['Q?'], 'api_key': ''})
    assert response.status_code == 400


@pytest.mark.parametrize('limit, expected', [(1, {'1'}), (2, {'1', '2'}), (200, {'1', '2', '3'})])
@patch('backend.main.render_page', return_value=(Image.new('RGB', (5, 5)), []))
def test_batch_limits_processing_to_first_pages(mock_render, limit, expected):
    _seed_document()
    with patch('backend.main.TypeSafeClient') as factory:
        sdk = factory.return_value.__enter__.return_value
        sdk.system_one.return_value = _response()
        response = client.post('/api/documents/doc-batch/evaluate-batch',
                               json={'questions': ['Q?'], 'api_key': 'test-key', 'page_limit': limit})
    assert response.status_code == 200
    assert set(response.json()['page_stats']) == expected
    assert response.json()['page_count'] == len(expected)
    assert sdk.system_one.call_count == min(limit, 2)
    assert mock_render.call_count == min(limit, 2)


@pytest.mark.parametrize('limit', [0, -1, 201, 1.5, True, '2'])
def test_batch_rejects_invalid_page_limits(limit):
    _seed_document()
    with patch('backend.main.TypeSafeClient') as factory:
        response = client.post('/api/documents/doc-batch/evaluate-batch',
                               json={'questions': ['Q?'], 'api_key': 'test-key', 'page_limit': limit})
    assert response.status_code == 422
    factory.assert_not_called()


@patch('backend.main.render_page', return_value=(Image.new('RGB', (5, 5)), []))
def test_batch_classify_sends_choices_as_criteria(mock_render):
    _seed_document()
    with patch('backend.main.httpx.Client') as factory:
        http = factory.return_value.__enter__.return_value
        http.post.return_value.json.return_value = {'answers': {'q1': {'probs': {'hard_drives': 0.8, 'mobile': 0.2}}}}
        response = client.post('/api/documents/doc-batch/evaluate-batch', json={
            'questions': ['Category?'], 'choices': ['Hard Drives: HDDs, SSDs', ' ', 'Mobile'], 'model': 'atom'})
    assert response.status_code == 200
    page = response.json()['page_stats']['1']
    assert page['answers']['q1']['probabilities'] == {'hard_drives': 0.8, 'mobile': 0.2}
    assert page['choice_keys'] == ['hard_drives', 'mobile']
    sent = http.post.call_args.kwargs['json']
    assert sent['state'] in ('Repeated', 'Total 100')
    # Named keys with descriptions, as in ATOM's docs; a bare name is its own description.
    assert sent['questions']['q1']['criteria'] == {'hard_drives': 'HDDs, SSDs', 'mobile': 'Mobile'}
    # The UI's curl dialog is built from this; it must be exactly what was posted.
    request = response.json()['page_stats']['1']['request']
    assert request == {'url': 'https://at0m.pienomial.com/decide/v0',
                       'body': {'state': 'Repeated', 'questions': sent['questions']}}


@pytest.mark.parametrize('choices', [['Laptop', ''], ['Laptop', 'laptop: notebooks'], ['Laptop', ': no name']])
def test_batch_classify_rejects_bad_choices(choices):
    _seed_document()
    with patch('backend.main.httpx.Client') as factory:
        response = client.post('/api/documents/doc-batch/evaluate-batch', json={
            'questions': ['Category?'], 'choices': choices, 'model': 'atom'})
    assert response.status_code == 400
    factory.assert_not_called()


@pytest.mark.parametrize('choices, expected_state', [
    (['Laptop', 'Mobile'], '## Invoice | Laptop | 1 |'),  # classification: raw OCR, newlines -> spaces
    ([], 'Invoice\nLaptop 1'),                            # extraction: cleaned chunks, unchanged
])
@patch('backend.main.render_page', return_value=(Image.new('RGB', (5, 5)), []))
def test_classification_uses_raw_ocr_text(mock_render, choices, expected_state):
    items = [dict(id=1, page=1, text='Invoice'), dict(id=2, page=1, text='Laptop 1')]
    store.put('doc-ocr', data=b'%PDF', items=items, turns={}, page_count=1,
              raw_ocr={1: '## Invoice\n| Laptop | 1 |'})
    with patch('backend.main.httpx.Client') as factory:
        http = factory.return_value.__enter__.return_value
        http.post.return_value.json.return_value = {'answers': {'q1': {'probs': {'0': 1.0}}}}
        response = client.post('/api/documents/doc-ocr/evaluate-batch',
                               json={'questions': ['Q?'], 'choices': choices, 'model': 'atom'})
    assert response.status_code == 200
    assert http.post.call_args.kwargs['json']['state'] == expected_state
