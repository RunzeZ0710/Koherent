from koherent.ai.embeddings import NIMEmbedder, _response_to_vectors


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


class _CapturingClient:
    """Stands in for the OpenAI SDK client; records the embeddings call."""

    def __init__(self):
        self.kwargs = None
        outer = self

        class _Embeddings:
            def create(self, **kwargs):
                outer.kwargs = kwargs

                class _Item:
                    embedding = [0.0]

                class _Response:
                    data = [_Item() for _ in kwargs["input"]]

                return _Response()

        self.embeddings = _Embeddings()


def test_embed_defaults_to_passage_input_type():
    fake_sdk = _CapturingClient()
    embedder = NIMEmbedder(api_key="test-key", client=fake_sdk)
    embedder.embed(["some text"])
    assert fake_sdk.kwargs["extra_body"]["input_type"] == "passage"


def test_embed_input_type_override():
    fake_sdk = _CapturingClient()
    embedder = NIMEmbedder(api_key="test-key", client=fake_sdk)
    embedder.embed(["a question"], input_type="query")
    assert fake_sdk.kwargs["extra_body"]["input_type"] == "query"
