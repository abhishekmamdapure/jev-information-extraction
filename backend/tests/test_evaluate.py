import os
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import store
from backend.main import app

client = TestClient(app)


def _seed_document():
    items = [dict(id=1, page=1, text='Repeated'), dict(id=2, page=1, text='Total 100')]
    store.put('doc-eval', data=b'%PDF', items=items, turns={}, page_count=1)


def _response():
    return SimpleNamespace(
        answers={'q1': SimpleNamespace(probabilities={'0': 0.2, '1': 0.9})},
        usage=SimpleNamespace(input_tokens=100, output_tokens=10), model='jev-latest')


def test_evaluate_page_returns_answers():
    _seed_document()
    with patch('backend.main.TypeSafeClient') as factory:
        client_mock = factory.return_value.__enter__.return_value
        client_mock.system_one.return_value = _response()
        response = client.post('/api/documents/doc-eval/pages/1/evaluate',
                                json={'questions': ['What is the total?'], 'api_key': 'test-key'})
    assert response.status_code == 200
    body = response.json()
    assert body['answers']['q1']['probabilities'] == {'0': 0.2, '1': 0.9}
    assert body['model'] == 'jev-latest'
    factory.assert_called_once_with(api_key='test-key')


def test_evaluate_page_missing_api_key_is_400():
    _seed_document()
    with patch.dict(os.environ, {'TYPESAFE_API_KEY': 'server-key-must-not-be-used'}):
        response = client.post('/api/documents/doc-eval/pages/1/evaluate',
                                json={'questions': ['Q?'], 'api_key': ''})
    assert response.status_code == 400
    assert 'API key' in response.json()['detail']


def test_evaluate_page_no_questions_is_400():
    _seed_document()
    response = client.post('/api/documents/doc-eval/pages/1/evaluate',
                            json={'questions': [], 'api_key': 'test-key'})
    assert response.status_code == 400
    assert 'question' in response.json()['detail']


def test_evaluate_page_redacts_key_from_error():
    _seed_document()
    with patch('backend.main.TypeSafeClient') as factory:
        factory.return_value.__enter__.return_value.system_one.side_effect = RuntimeError('secret-key failed')
        response = client.post('/api/documents/doc-eval/pages/1/evaluate',
                                json={'questions': ['Q?'], 'api_key': 'secret-key'})
    assert response.status_code == 502
    assert 'secret-key' not in response.json()['detail']


def test_evaluate_page_atom_sends_items_as_choice_without_key():
    _seed_document()
    with patch('backend.main.httpx.Client') as factory:
        http = factory.return_value.__enter__.return_value
        http.post.return_value.json.return_value = {
            'answers': {'q1': {'type': 'choice', 'probs': {'0': 0.1, '1': 0.9}, 'choice': '1'}}, 'ms': 5.0}
        response = client.post('/api/documents/doc-eval/pages/1/evaluate',
                                json={'questions': ['What is the total?'], 'model': 'atom'})
    assert response.status_code == 200
    body = response.json()
    assert body['answers']['q1']['probabilities'] == {'0': 0.1, '1': 0.9}
    assert body['model'] == 'at0m-v0'
    question = http.post.call_args.kwargs['json']['questions']['q1']
    assert question == {'type': 'choice', 'instructions': 'What is the total?',
                        'criteria': {'0': 'Repeated', '1': 'Total 100'}}
