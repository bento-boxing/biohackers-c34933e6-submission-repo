from unittest.mock import Mock
import pytest
import requests
from devils_advocate.http_client import JsonClient, RetrievalError

def test_cache_parameters_and_defensive_copies():
    client = JsonClient()
    response = Mock()
    response.json.return_value = {'items': [1]}
    client.session.get = Mock(return_value=response)
    result = client.get('https://example.org', {'q': 'one'})
    result['items'].append(2)
    assert client.get('https://example.org', {'q': 'one'}) == {'items': [1]}
    assert client.session.get.call_count == 1
    client.get('https://example.org', {'q': 'two'})
    assert client.session.get.call_count == 2
    assert client.session.get.call_args.kwargs['timeout'] == (5, 20)

def test_timeout_is_a_clear_retrieval_error():
    client = JsonClient()
    client.session.get = Mock(side_effect=requests.Timeout('timed out'))
    with pytest.raises(RetrievalError, match='example.org'):
        client.get('https://example.org')
