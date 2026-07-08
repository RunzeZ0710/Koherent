from koherent.ai.chat import NIMChatClient, _response_to_text
from koherent.ai.real import RealAIClient


class _Msg:
    content = "generated answer"


class _Choice:
    message = _Msg()


class _Response:
    choices = [_Choice()]


class _CapturingChatSDK:
    def __init__(self):
        self.kwargs = None
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.kwargs = kwargs
                return _Response()

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


def test_response_to_text_reads_first_choice():
    assert _response_to_text(_Response()) == "generated answer"


def test_generate_sends_system_and_user_messages():
    sdk = _CapturingChatSDK()
    chat = NIMChatClient(api_key="test-key", model="test/model", client=sdk)
    out = chat.generate("be helpful", "what is elasticity?")
    assert out == "generated answer"
    assert sdk.kwargs["model"] == "test/model"
    assert sdk.kwargs["messages"] == [
        {"role": "system", "content": "be helpful"},
        {"role": "user", "content": "what is elasticity?"},
    ]
    assert sdk.kwargs["temperature"] == 0.2


class _StubEmbedder:
    def __init__(self):
        self.calls = []

    def embed(self, texts, *, input_type=None):
        self.calls.append((texts, input_type))
        return [[1.0, 2.0] for _ in texts]


class _StubChat:
    def generate(self, system_prompt, user_prompt):
        return f"chat:{user_prompt}"


def test_real_client_delegates_generate_and_embed_query():
    embedder = _StubEmbedder()
    real = RealAIClient(transcriber=object(), embedder=embedder, chat=_StubChat())
    assert real.generate("sys", "hi") == "chat:hi"
    assert real.embed_query("a question") == [1.0, 2.0]
    assert embedder.calls == [(["a question"], "query")]
