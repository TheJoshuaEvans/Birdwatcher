"""
Talking to a chat completion API: the providers on offer, finding the API key,
listing a provider's models, and sending a conversation.

Every provider speaks OpenAI's chat completion format, so one client (the
`openai` SDK, as the course teaches) reaches all of them; only the address,
the key and the model name change.

Joshua Evans, 2026-11-18 (written with Claude Opus 5.5)
"""

import logging
import ssl
import time
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from http import HTTPStatus

import openai
import truststore

OPENROUTER, GEMINI, OPENAI, LOCAL, CUSTOM = (
    "openrouter",
    "gemini",
    "openai",
    "local",
    "custom",
)  # provider ids
DEFAULT_PROVIDER = OPENROUTER
FREE_ROUTER = "openrouter/free"  # routes each request to any free model
TIMEOUT = 120  # seconds to wait for an answer (thinking models can be slow)
SAVED_SOURCE = "saved in Birdwatcher"
TOKENS_PER_PRICE = 1_000_000  # prices are shown per million tokens
# The SDK insists on a key; this one is never sent (see _key_headers).
UNSENT_KEY = "no-key"

_log = logging.getLogger(__name__)  # never given the key (see core.log)


@dataclass(frozen=True)
class Provider:
    """
    A chat completion service Birdwatcher can talk to.

    Attributes:
        id (str): The id saved in the settings, e.g. "openrouter".
        name (str): Its name for people, e.g. "OpenRouter".
        description (str): A few words on what it offers.
        base_url (str | None): The address of its API; None for the custom
            provider, whose address the user enters.
        key_variable (str | None): The environment variable that holds its
            key (as the course sets it up), or None when it has none.
        needs_key (bool): Whether requests need an API key.
        default_model (str): The model chosen when the provider is picked
            ("" when the user must choose one).
    """

    id: str
    name: str
    description: str
    base_url: str | None
    key_variable: str | None
    needs_key: bool
    default_model: str = ""


PROVIDERS: Mapping[str, Provider] = {
    OPENROUTER: Provider(
        OPENROUTER,
        "OpenRouter",
        "one key for models from every company",
        "https://openrouter.ai/api/v1",
        "OPENROUTER_API_KEY",
        True,
        FREE_ROUTER,
    ),
    GEMINI: Provider(
        GEMINI,
        "Gemini",
        "Google's models, with a Google AI Studio key",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "GEMINI_API_KEY",
        True,
    ),
    OPENAI: Provider(
        OPENAI,
        "OpenAI",
        "OpenAI's models, with an OpenAI platform key",
        "https://api.openai.com/v1",
        "OPENAI_API_KEY",
        True,
    ),
    LOCAL: Provider(
        LOCAL,
        "Local",
        "Ollama on this computer, no key needed",
        "http://localhost:11434/v1",
        None,
        False,
    ),
    CUSTOM: Provider(
        CUSTOM,
        "Custom URL",
        "any address that speaks OpenAI's format (a key is optional)",
        None,
        None,
        False,
    ),
}


@dataclass(frozen=True)
class ApiKey:
    """
    An API key and where it came from. Its repr never shows the key.

    Attributes:
        value (str): The key itself.
        source (str): Where it came from, for people: "saved in Birdwatcher"
            or the name of the environment variable.
    """

    value: str = field(repr=False)
    source: str


@dataclass(frozen=True)
class KeyStore:
    """
    Where Birdwatcher saves API keys (the system's keyring), one per provider.

    Attributes:
        get (Callable[[str], str | None]): The saved key for a provider id,
            or None.
        set (Callable[[str, str], object]): Saves a key for a provider id,
            replacing any earlier one. Raises OSError when it cannot be saved.
        delete (Callable[[str], object]): Forgets a provider's saved key (no
            error when there is none).
    """

    get: Callable[[str], str | None]
    set: Callable[[str, str], object]
    delete: Callable[[str], object]


def memory_key_store(keys=None):
    """
    A KeyStore held in memory, so nothing outlives the program: for tests,
    and for pages used without the system's keyring.

    Args:
        keys (dict[str, str] | None): Saved keys by provider id to start
            with; the store reads and changes this dictionary.

    Returns:
        KeyStore: The store.
    """
    keys = {} if keys is None else keys
    return KeyStore(
        get=keys.get,
        set=keys.__setitem__,
        delete=lambda provider_id: keys.pop(provider_id, None),
    )


@dataclass(frozen=True)
class Connection:
    """
    Everything needed to reach a model.

    Attributes:
        provider (Provider): The provider.
        base_url (str): The API's address (the provider's, or the one the
            user entered for the custom provider).
        key (ApiKey | None): The key to send, or None to send none.
        model (str): The model's name, as the provider spells it.
    """

    provider: Provider
    base_url: str
    key: ApiKey | None
    model: str


@dataclass(frozen=True)
class Reply:
    """
    A model's answer to a conversation.

    Attributes:
        text (str): What the model wrote.
        model (str): The model that answered, as the provider reports it (a
            router such as "openrouter/free" names the model it chose).
        input_tokens (int | None): Tokens read, when the provider reports it.
        output_tokens (int | None): Tokens written, when the provider reports
            it.
        seconds (float): How long the request took.
    """

    text: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    seconds: float


@dataclass(frozen=True)
class ModelInfo:
    """
    A model a provider offers.

    Attributes:
        id (str): The name to send in requests, e.g. "openrouter/free".
        name (str | None): Its name for people, when the provider gives one.
        context_length (int | None): How many tokens it reads at most, when
            known.
        input_price (float | None): US dollars per million tokens read, when
            known (0 for free models).
        output_price (float | None): US dollars per million tokens written,
            when known.
    """

    id: str
    name: str | None = None
    context_length: int | None = None
    input_price: float | None = None
    output_price: float | None = None


class AiError(Exception):
    """
    A request could not be made or failed; the message is for people and
    never contains the API key.

    Attributes:
        retry_may_help (bool): True when the same request may well succeed
            if sent again: the model answered without text, the provider
            failed on its side (5xx) or did not answer in time. A router such
            as openrouter/free may then pick another model. False when it
            would fail the same way: the key or model was refused, the rate
            was limited, the provider could not be reached, or the settings
            are unusable.
    """

    def __init__(self, message, retry_may_help=False):
        super().__init__(message)
        self.retry_may_help = retry_may_help


def model_warning(provider_id, model):
    """
    A caution to show beside a chosen model, when it needs one.

    Args:
        provider_id (str): The chosen provider's id.
        model (str): The chosen model (surrounding spaces are ignored).

    Returns:
        str | None: For OpenRouter's free router (openrouter/free), that
            each request goes to whichever free model is available, so
            answers can differ between requests and runs; otherwise None.
    """
    if provider_id == OPENROUTER and model.strip() == FREE_ROUTER:
        return (
            f"{FREE_ROUTER} sends each request to whichever free model is "
            "available, often a small one, so answers can differ between "
            "requests and between runs. Choose a model with PICK… for steadier "
            "results."
        )
    return None


def find_key(provider, saved, environ):
    """
    The API key to use for a provider: a key saved in Birdwatcher wins over
    the provider's environment variable.

    Args:
        provider (Provider): The provider.
        saved (str | None): The key saved in Birdwatcher for it, if any.
        environ (Mapping[str, str]): The environment variables.

    Returns:
        ApiKey | None: The key with its source, or None when neither is set
            (blank values count as not set).
    """
    if saved and saved.strip():
        return ApiKey(saved.strip(), SAVED_SOURCE)
    variable = provider.key_variable
    value = environ.get(variable, "").strip() if variable else ""
    return ApiKey(value, variable) if value else None


def connect(provider_id, model, key, custom_url=""):
    """
    Check the chosen settings and put them together for a request.

    Args:
        provider_id (str): The chosen provider's id.
        model (str): The chosen model (surrounding spaces are ignored).
        key (ApiKey | None): The key found for the provider.
        custom_url (str): The address entered for the custom provider
            (ignored for the others).

    Returns:
        Connection: The connection to use.

    Raises:
        AiError: The provider id is unknown, the custom provider has no
            address, the provider needs a key and none was found (the message
            names its environment variable), or no model is chosen.
    """
    connection = listing(provider_id, key, custom_url)
    provider = connection.provider
    if provider.needs_key and key is None:
        raise AiError(
            f"No API key for {provider.name}: set the {provider.key_variable} "
            "environment variable, or save a key in Birdwatcher."
        )
    if not model.strip():
        raise AiError("Choose a model first.")
    return replace(connection, model=model.strip())


def listing(provider_id, key, custom_url=""):
    """
    Settings for listing a provider's models: like connect, but no model is
    needed and a missing key is no error (some providers, OpenRouter among
    them, list their models without one).

    Args:
        provider_id (str): The chosen provider's id.
        key (ApiKey | None): The key found for the provider.
        custom_url (str): As for connect.

    Returns:
        Connection: The connection to list models with (its model is "").

    Raises:
        AiError: The provider id is unknown, or the custom provider has no
            address.
    """
    provider = PROVIDERS.get(provider_id)
    if provider is None:
        raise AiError(f"Birdwatcher does not know the provider '{provider_id}'.")
    base_url = provider.base_url or custom_url.strip()
    if not base_url:
        raise AiError("Enter the address of the custom provider's API.")
    return Connection(provider, base_url, key, "")


def chat(connection, messages, transport=None):
    """
    Send a conversation and return the model's answer.

    Args:
        connection (Connection): Where to send it (it must name a model).
        messages (Sequence[Mapping[str, str]]): The conversation so far, as
            {"role": ..., "content": ...} dictionaries ("system", "user" or
            "assistant"), oldest first.
        transport (httpx2.BaseTransport | None): Carries the HTTP requests;
            None means the network (with the system's trusted certificates).

    Returns:
        Reply: The answer.

    Raises:
        AiError: The provider could not be reached, did not answer within
            TIMEOUT, refused the key or the model, limited the rate, failed,
            or sent no text. The message names the provider and repeats what
            it said, when it said something.
    """
    messages = list(messages)
    _log.info(
        "request to %s, model %s at %s: %d messages",
        connection.provider.name,
        connection.model,
        connection.base_url,
        len(messages),
    )
    for message in messages:
        _log.debug("%s:\n%s", message["role"], message["content"])
    started = time.monotonic()
    try:
        with _explained(connection):
            completion = _client(connection, transport).chat.completions.create(
                model=connection.model,
                messages=messages,
                extra_headers=_key_headers(connection),
            )
    except AiError as error:
        _log.warning(
            "request failed after %.1f s: %s", time.monotonic() - started, error
        )
        raise
    seconds = time.monotonic() - started
    choice = completion.choices[0] if completion.choices else None
    text = choice.message.content if choice else None
    usage = completion.usage
    _log.info(
        "answer from %s in %.1f s: %s tokens read, %s written, finish reason %s",
        completion.model or connection.model,
        seconds,
        usage.prompt_tokens if usage else "?",
        usage.completion_tokens if usage else "?",
        choice.finish_reason if choice else "no choices",
    )
    _log.debug("answer:\n%s", text)
    if not text:
        reason = choice.finish_reason if choice else "no choices"
        raise AiError(
            f"{connection.model} sent no text (finish reason: {reason}). "
            "Try again, or choose another model.",
            retry_may_help=True,
        )
    return Reply(
        text=text,
        model=completion.model or connection.model,
        input_tokens=usage.prompt_tokens if usage else None,
        output_tokens=usage.completion_tokens if usage else None,
        seconds=seconds,
    )


def list_models(connection, transport=None):
    """
    The models a provider offers.

    Args:
        connection (Connection): The provider to ask (its model is ignored;
            the key is sent when there is one).
        transport (httpx2.BaseTransport | None): As for chat.

    Returns:
        list[ModelInfo]: The models, sorted by id. Names, context lengths and
            prices are filled in when the provider lists them (OpenRouter
            does); prices are converted to dollars per million tokens, and a
            price the provider cannot state in advance (a router's) is None.

    Raises:
        AiError: As for chat.
    """
    _log.info(
        "listing the models of %s at %s", connection.provider.name, connection.base_url
    )
    try:
        with _explained(connection):
            page = _client(connection, transport).models.list(
                extra_headers=_key_headers(connection)
            )
    except AiError as error:
        _log.warning("listing models failed: %s", error)
        raise
    models = [_model_info(model) for model in page.data]
    _log.info("%d models listed", len(models))
    return sorted(models, key=lambda model: model.id)


def _client(connection, transport):
    if transport is None:
        http = openai.DefaultHttpxClient(
            verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        )
    else:
        http = openai.DefaultHttpxClient(transport=transport)
    key = connection.key.value if connection.key else UNSENT_KEY
    return openai.OpenAI(
        base_url=connection.base_url,
        api_key=key,
        timeout=TIMEOUT,
        max_retries=0,  # the person retries; a silent wait would look stuck
        http_client=http,
    )


def _key_headers(connection):
    """Per-request headers: with no key, no Authorization header at all."""
    return None if connection.key else {"Authorization": openai.Omit()}


@contextmanager
def _explained(connection):
    """Turns the SDK's errors into an AiError that explains them."""
    try:
        yield
    except openai.OpenAIError as error:
        raise AiError(
            _explain(connection, error), retry_may_help=_may_pass(error)
        ) from error


def _may_pass(error):
    """Whether sending the same request again may succeed (see AiError)."""
    if isinstance(error, openai.APITimeoutError):  # before its parent class
        return True
    if isinstance(error, openai.APIStatusError):
        return error.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR
    return False


def _explain(connection, error):
    name = connection.provider.name
    if isinstance(error, openai.APITimeoutError):
        return f"No answer from {name} within {TIMEOUT} seconds."
    if isinstance(error, openai.APIConnectionError):
        return f"Could not reach {name} at {connection.base_url}."
    if not isinstance(error, openai.APIStatusError):
        return f"{name}: {error}"
    said = _server_message(error)
    if isinstance(error, openai.AuthenticationError):
        source = connection.key.source if connection.key else "no key sent"
        return f"{name} did not accept the API key ({source}): {said}"
    if isinstance(error, openai.NotFoundError):
        return f"{name} has no model '{connection.model}' (or no such page): {said}"
    if isinstance(error, openai.RateLimitError):
        return (
            f"{name} limited the rate of requests; wait a little and try again "
            f"(free models have low limits): {said}"
        )
    return f"{name} answered with error {error.status_code}: {said}"


def _server_message(error):
    """What the server said, from its JSON error body when it sent one."""
    body = error.body
    if isinstance(body, dict) and isinstance(body.get("message"), str):
        return body["message"]
    return error.message


def _model_info(model):
    extra = model.model_extra or {}
    pricing = extra.get("pricing")
    pricing = pricing if isinstance(pricing, dict) else {}
    name = extra.get("name")
    length = extra.get("context_length")
    return ModelInfo(
        id=model.id,
        name=name if isinstance(name, str) else None,
        context_length=length if isinstance(length, int) else None,
        input_price=_per_million(pricing.get("prompt")),
        output_price=_per_million(pricing.get("completion")),
    )


def _per_million(per_token):
    """A price per token (OpenRouter sends strings) as dollars per million
    tokens; negative or unreadable prices (a router's "-1") are None."""
    try:
        price = float(per_token)
    except (TypeError, ValueError):
        return None
    return None if price < 0 else round(price * TOKENS_PER_PRICE, 6)
