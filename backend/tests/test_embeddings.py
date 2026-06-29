from koherent.ai.embeddings import _response_to_vectors


class _Item:
    def __init__(self, embedding):
        self.embedding = embedding


class _Response:
    def __init__(self, data):
        self.data = data


def test_response_to_vectors_preserves_order_and_shape():
    response = _Response([_Item([0.1, 0.2]), _Item([0.3, 0.4])])
    assert _response_to_vectors(response) == [[0.1, 0.2], [0.3, 0.4]]


def test_response_to_vectors_empty():
    assert _response_to_vectors(_Response([])) == []
