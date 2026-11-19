"""
Contract tests for birdwatcher.core.ai.

Requests go to a fake server (httpx2.MockTransport) through the real openai
SDK, so the tests check what is sent and how each kind of answer is read
without touching the network.

Joshua Evans, 2026-11-18 (written with Claude Opus 5.5)
"""

import json

import httpx2
import pytest

from birdwatcher.core.ai import (
    CUSTOM,
    LOCAL,
    OPENROUTER,
    PROVIDERS,
    TIMEOUT,
    AiError,
    ApiKey,
    Connection,
    ModelInfo,
    chat,
    connect,
    find_key,
    list_models,
    listing,
    memory_key_store,
)

SECRET = "sk-or-v1-secret-test-key"
CONVERSATION = [
    {"role": "system", "content": "Answer in one word."},
    {"role": "user", "content": "Capital of France?"},
]


class FakeServer:
    """Answers every request with a handler's response and records the
    requests."""

    def __init__(self, respond):
        self.requests = []
        self._respond = respond
        self.transport = httpx2.MockTransport(self._handle)

    def _handle(self, request):
        self.requests.append(request)
        return self._respond(request)


def answering(status, body):
    return FakeServer(lambda request: httpx2.Response(status, json=body))


def completion(text="Paris", model="google/gemma-4-31b-it:free", usage=True):
    body = {
        "id": "gen-1",
        "object": "chat.completion",
        "created": 1_700_000_000,
        "model": model,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": text},
            }
        ],
    }
    if usage:
        body["usage"] = {
            "prompt_tokens": 12,
            "completion_tokens": 3,
            "total_tokens": 15,
        }
    return body


def openrouter(model="openrouter/free", key=SECRET):
    return Connection(
        PROVIDERS[OPENROUTER],
        PROVIDERS[OPENROUTER].base_url,
        None if key is None else ApiKey(key, "OPENROUTER_API_KEY"),
        model,
    )


def custom(url="http://localhost:1234/v1", key=None):
    return Connection(PROVIDERS[CUSTOM], url, key, "my-model")


# find_key


def test_a_saved_key_wins_over_the_environment():
    key = find_key(PROVIDERS[OPENROUTER], "saved", {"OPENROUTER_API_KEY": "env"})
    assert key == ApiKey("saved", "saved in Birdwatcher")


def test_the_environment_variable_is_used_when_nothing_is_saved():
    key = find_key(PROVIDERS[OPENROUTER], None, {"OPENROUTER_API_KEY": "env"})
    assert key == ApiKey("env", "OPENROUTER_API_KEY")


@pytest.mark.parametrize(
    ("saved", "environ"),
    [
        (None, {}),
        ("", {"OPENROUTER_API_KEY": "  "}),
        ("   ", {"GEMINI_API_KEY": "another provider's key"}),
    ],
)
def test_no_key_when_neither_is_set(saved, environ):
    assert find_key(PROVIDERS[OPENROUTER], saved, environ) is None


def test_a_blank_saved_key_falls_back_to_the_environment():
    key = find_key(PROVIDERS[OPENROUTER], " ", {"OPENROUTER_API_KEY": "env"})
    assert key == ApiKey("env", "OPENROUTER_API_KEY")


def test_a_provider_without_a_variable_only_uses_a_saved_key():
    assert find_key(PROVIDERS[LOCAL], None, {"OPENAI_API_KEY": "x"}) is None
    assert find_key(PROVIDERS[CUSTOM], "mine", {}) == ApiKey(
        "mine", "saved in Birdwatcher"
    )


def test_a_key_never_shows_in_its_repr():
    assert SECRET not in repr(ApiKey(SECRET, "OPENROUTER_API_KEY"))


def test_a_memory_key_store_keeps_keys_in_the_given_dictionary():
    keys = {"gemini": "AIza-1"}
    store = memory_key_store(keys)
    store.set("openrouter", "sk-or-2")
    store.delete("gemini")
    store.delete("never-saved")
    assert store.get("openrouter") == "sk-or-2"
    assert store.get("gemini") is None
    assert keys == {"openrouter": "sk-or-2"}


# connect


def test_connect_uses_the_providers_address():
    key = ApiKey(SECRET, "OPENROUTER_API_KEY")
    connection = connect(OPENROUTER, "  openrouter/free ", key)
    assert connection == Connection(
        PROVIDERS[OPENROUTER], PROVIDERS[OPENROUTER].base_url, key, "openrouter/free"
    )


def test_connect_uses_the_entered_address_for_the_custom_provider():
    connection = connect(CUSTOM, "my-model", None, "  http://localhost:1234/v1 ")
    assert connection.base_url == "http://localhost:1234/v1"
    assert connection.key is None


def test_a_local_provider_needs_no_key():
    assert connect(LOCAL, "llama3", None).key is None


def test_a_missing_key_names_the_environment_variable():
    with pytest.raises(AiError, match="OPENROUTER_API_KEY"):
        connect(OPENROUTER, "openrouter/free", None)


@pytest.mark.parametrize(
    ("provider_id", "model", "url", "words"),
    [
        ("nonsense", "m", "", "nonsense"),
        (CUSTOM, "m", "  ", "address"),
        (LOCAL, "  ", "", "model"),
    ],
)
def test_unusable_settings_are_refused(provider_id, model, url, words):
    with pytest.raises(AiError, match=words):
        connect(provider_id, model, None, url)


def test_listing_needs_neither_a_model_nor_a_key():
    assert listing(OPENROUTER, None) == Connection(
        PROVIDERS[OPENROUTER], PROVIDERS[OPENROUTER].base_url, None, ""
    )
    assert listing(CUSTOM, None, " http://localhost:1234/v1 ").base_url == (
        "http://localhost:1234/v1"
    )


@pytest.mark.parametrize(
    ("provider_id", "url", "words"),
    [("nonsense", "", "nonsense"), (CUSTOM, " ", "address")],
)
def test_listing_refuses_unusable_settings(provider_id, url, words):
    with pytest.raises(AiError, match=words):
        listing(provider_id, None, url)


# chat


def test_chat_sends_the_conversation_and_reads_the_answer():
    server = answering(200, completion())
    reply = chat(openrouter(), CONVERSATION, transport=server.transport)

    assert reply.text == "Paris"
    assert reply.model == "google/gemma-4-31b-it:free"
    assert (reply.input_tokens, reply.output_tokens) == (12, 3)
    assert reply.seconds >= 0
    (request,) = server.requests
    assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {SECRET}"
    sent = json.loads(request.content)
    assert sent["model"] == "openrouter/free"
    assert sent["messages"] == CONVERSATION


def test_token_counts_are_none_when_not_reported():
    server = answering(200, completion(usage=False))
    reply = chat(openrouter(), CONVERSATION, transport=server.transport)
    assert (reply.input_tokens, reply.output_tokens) == (None, None)


def test_no_key_sends_no_key_even_with_openais_variable_set(monkeypatch):
    # The SDK reads OPENAI_API_KEY by itself; it must not leak to other hosts.
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key-for-another-host")
    server = answering(200, completion())
    chat(custom(), CONVERSATION, transport=server.transport)
    (request,) = server.requests
    assert "openai-key-for-another-host" not in str(request.headers)
    assert str(request.url) == "http://localhost:1234/v1/chat/completions"


@pytest.mark.parametrize(
    ("status", "words"),
    [
        (401, ["OpenRouter", "OPENROUTER_API_KEY", "Invalid credentials"]),
        (404, ["OpenRouter", "openrouter/free", "Invalid credentials"]),
        (429, ["OpenRouter", "rate", "Invalid credentials"]),
        (500, ["OpenRouter", "500", "Invalid credentials"]),
        (402, ["OpenRouter", "402", "Invalid credentials"]),
    ],
)
def test_refusals_explain_themselves_without_the_key(status, words):
    server = answering(status, {"error": {"message": "Invalid credentials"}})
    with pytest.raises(AiError) as caught:
        chat(openrouter(), CONVERSATION, transport=server.transport)
    message = str(caught.value)
    for word in words:
        assert word.lower() in message.lower()
    assert SECRET not in message


def test_an_unreachable_provider_is_reported():
    def refuse(request):
        raise httpx2.ConnectError("connection refused", request=request)

    with pytest.raises(AiError, match="reach") as caught:
        chat(custom(), CONVERSATION, transport=FakeServer(refuse).transport)
    assert "localhost:1234" in str(caught.value)


def test_a_slow_provider_is_reported():
    def stall(request):
        raise httpx2.ReadTimeout("timed out", request=request)

    with pytest.raises(AiError, match=str(TIMEOUT)):
        chat(openrouter(), CONVERSATION, transport=FakeServer(stall).transport)


def test_an_answer_without_text_is_an_error():
    server = answering(200, completion(text=None))
    with pytest.raises(AiError, match="no text"):
        chat(openrouter(), CONVERSATION, transport=server.transport)


# list_models


def test_openrouter_models_come_with_names_and_prices_per_million():
    server = answering(
        200,
        {
            "data": [
                {
                    "id": "openrouter/free",
                    "name": "Free Models Router",
                    "context_length": 200000,
                    "pricing": {"prompt": "0", "completion": "0"},
                },
                {
                    "id": "anthropic/claude-opus-5.5",
                    "name": "Anthropic: Claude Opus 5.5",
                    "context_length": 1000000,
                    "pricing": {"prompt": "0.000004", "completion": "0.00002"},
                },
                {
                    "id": "openrouter/auto",
                    "name": "Auto Router",
                    "context_length": 2000000,
                    "pricing": {"prompt": "-1", "completion": "-1"},
                },
            ]
        },
    )
    models = list_models(openrouter(), transport=server.transport)

    assert models == [
        ModelInfo(
            "anthropic/claude-opus-5.5",
            "Anthropic: Claude Opus 5.5",
            1000000,
            4.0,
            20.0,
        ),
        ModelInfo("openrouter/auto", "Auto Router", 2000000, None, None),
        ModelInfo("openrouter/free", "Free Models Router", 200000, 0.0, 0.0),
    ]
    (request,) = server.requests
    assert str(request.url) == "https://openrouter.ai/api/v1/models"
    assert request.headers["authorization"] == f"Bearer {SECRET}"


def test_plain_model_lists_give_ids_only():
    server = answering(
        200,
        {
            "object": "list",
            "data": [
                {"id": "zeta", "object": "model", "created": 0, "owned_by": "me"},
                {"id": "alpha", "object": "model", "created": 0, "owned_by": "me"},
            ],
        },
    )
    assert list_models(custom(), transport=server.transport) == [
        ModelInfo("alpha"),
        ModelInfo("zeta"),
    ]


def test_models_can_be_listed_without_a_key():
    server = answering(200, {"data": []})
    assert list_models(openrouter(key=None), transport=server.transport) == []


def test_a_failed_model_list_is_an_error():
    server = answering(401, {"error": {"message": "Invalid credentials"}})
    with pytest.raises(AiError, match="Invalid credentials"):
        list_models(openrouter(), transport=server.transport)
