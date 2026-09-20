from backend import store


def test_put_then_get_roundtrips():
    store.put('abc', data=b'%PDF-1.4', items=[{'id': 1}], turns={1: 0}, page_count=1)
    document = store.get('abc')
    assert document == {'data': b'%PDF-1.4', 'items': [{'id': 1}], 'turns': {1: 0}, 'page_count': 1}


def test_get_missing_returns_none():
    assert store.get('does-not-exist') is None
