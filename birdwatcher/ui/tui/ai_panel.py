"""
The setup page's AI MODEL tab: the chat completion provider, its API key, the
model, and a test chat to try them.

Joshua Evans, 2026-11-18 (written with Claude Opus 5.5)
"""

import logging
from functools import partial

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.widgets import Button, Input, RadioButton, RadioSet, Static

from birdwatcher.core.ai import (
    CUSTOM,
    DEFAULT_PROVIDER,
    LOCAL,
    PROVIDERS,
    SAVED_SOURCE,
    AiError,
    connect,
    find_key,
    listing,
    model_warning,
)
from birdwatcher.ui.tui.key_dialog import KeyDialog
from birdwatcher.ui.tui.model_picker import ModelPicker, describe

PROVIDER_ID_PREFIX = "provider-"
_log = logging.getLogger(__name__)  # never given a key's value


class AiPanel(Vertical):
    """
    The AI settings and a test chat.

    PROVIDER: one choice per core.ai.PROVIDERS entry (#provider-<id>), with
    its description; the custom provider shows an address box (#ai-url).
    Choosing a provider puts its model back (the one last used with it on
    this page, or its default model).

    API KEY: #ai-key-status says which key is in use (one saved in
    Birdwatcher, or the provider's environment variable, by name), or that
    none is set or needed; it never shows a key. SET KEY... (#set-key) asks
    for one (key_dialog.KeyDialog) and saves it in `keys`; FORGET SAVED KEY
    (#forget-key, shown while one is saved) deletes it from `keys`. A
    keyring that cannot save shows its reason in the status.

    MODEL: a box for the model's name (#ai-model) and PICK... (#pick-model),
    which lists the provider's models (model_picker.ModelPicker) and fills
    the box with the choice; #ai-model-info then names it, with its price
    and context length. #ai-model-warning shows core.ai.model_warning for
    the provider and model in the box (OpenRouter's free router), and hides
    when there is none.

    TEST CHAT: a message typed in #chat-input and sent (Enter or #send-chat)
    goes, with the conversation so far, to the provider and model chosen
    above at that moment, on a background thread. #chat-log shows each
    message (YOU), each answer (AI) with the model that answered, its token
    counts and its time, and any failure as ERROR with its reason (a failed
    message is left out of the conversation). CLEAR (#clear-chat) starts a
    new conversation. Nothing on this tab is saved until the setup page is.

    Args:
        provider (str): The provider id to select at first (an unknown one
            selects core.ai.DEFAULT_PROVIDER).
        model (str): The model to fill in at first.
        url (str): The custom provider's address to fill in at first.
        keys (KeyStore): Where API keys are saved.
        environ (Mapping[str, str]): The environment variables (for keys).
        send_chat (Callable[[Connection, list[dict]], Reply]): Sends a
            conversation (core.ai.chat); raises AiError.
        fetch_models (Callable[[Connection], list[ModelInfo]]): Lists a
            provider's models (core.ai.list_models); raises AiError.
    """

    def __init__(self, provider, model, url, *, keys, environ, send_chat, fetch_models):
        super().__init__(id="ai-panel")
        self._provider = provider if provider in PROVIDERS else DEFAULT_PROVIDER
        self._models = {self._provider: model}  # the model last used per provider
        self._url = url
        self._keys = keys
        self._environ = environ
        self._send_chat = send_chat
        self._fetch_models = fetch_models
        self._history = []  # the test chat's conversation
        self._conversation = 0  # counts CLEARs, so a late answer is dropped
        self._waiting = False

    @property
    def values(self):
        """
        The AI settings as chosen on the tab.

        Returns:
            tuple[str, str, str]: The provider id, the model (without
                surrounding spaces) and the custom address (likewise).
        """
        return (
            self._provider,
            self.query_one("#ai-model", Input).value.strip(),
            self.query_one("#ai-url", Input).value.strip(),
        )

    def compose(self) -> ComposeResult:
        yield Static("PROVIDER", classes="setup-section")
        with RadioSet(id="ai-provider"):
            for provider in PROVIDERS.values():
                yield RadioButton(
                    Content(f"{provider.name}: {provider.description}"),
                    value=provider.id == self._provider,
                    id=f"{PROVIDER_ID_PREFIX}{provider.id}",
                )
        url = Input(
            value=self._url, placeholder="http://localhost:1234/v1", id="ai-url"
        )
        url.display = self._provider == CUSTOM
        yield url
        yield Static("API KEY", classes="setup-section")
        yield Static(id="ai-key-status")
        with Horizontal(id="ai-key-buttons"):
            yield Button(Content("SET KEY…"), id="set-key")
            yield Button(Content("FORGET SAVED KEY"), id="forget-key")
        yield Static("MODEL", classes="setup-section")
        with Horizontal(id="ai-model-row"):
            yield Input(
                value=self._models[self._provider],
                placeholder="the provider's name for it, e.g. openrouter/free",
                id="ai-model",
            )
            yield Button(Content("PICK…"), id="pick-model")
        yield Static(id="ai-model-info")
        yield Static(id="ai-model-warning")
        yield Static("TEST CHAT", classes="setup-section")
        yield VerticalScroll(id="chat-log")
        with Horizontal(id="chat-row"):
            yield Input(
                placeholder="Send a message to the model above (Enter sends)",
                id="chat-input",
            )
            yield Button(Content("SEND"), id="send-chat")
            yield Button(Content("CLEAR"), id="clear-chat")

    def on_mount(self):
        self._show_key()
        self._show_model_warning()

    def on_input_changed(self, event: Input.Changed):
        if event.input.id == "ai-model":
            self._show_model_warning()

    def _show_model_warning(self):
        model = self.query_one("#ai-model", Input).value
        warning = model_warning(self._provider, model)
        shown = self.query_one("#ai-model-warning", Static)
        shown.update(Text(f"NOTE {warning}" if warning else "", style="italic"))
        shown.display = warning is not None

    # Provider

    def on_radio_set_changed(self, event: RadioSet.Changed):
        event.stop()
        model = self.query_one("#ai-model", Input)
        self._models[self._provider] = model.value
        self._provider = event.pressed.id.removeprefix(PROVIDER_ID_PREFIX)
        model.value = self._models.get(
            self._provider, PROVIDERS[self._provider].default_model
        )
        self.query_one("#ai-url", Input).display = self._provider == CUSTOM
        self.query_one("#ai-model-info", Static).update("")
        self._show_key()
        self._show_model_warning()

    # Key

    def _key(self):
        provider = PROVIDERS[self._provider]
        return find_key(provider, self._keys.get(provider.id), self._environ)

    def _show_key(self, problem=None):
        provider = PROVIDERS[self._provider]
        saved = self._keys.get(provider.id)
        key = self._key()
        if problem:
            status = Text(problem, style="bold red")
        elif key is not None and key.source == SAVED_SOURCE:
            status = Text("Using the key saved in Birdwatcher (in the system keyring).")
        elif key is not None:
            status = Text(f"Using the {key.source} environment variable.")
        elif provider.needs_key:
            status = Text(
                f"No key yet: set the {provider.key_variable} environment variable, "
                "or save one with SET KEY…"
            )
        elif provider.id == LOCAL:
            status = Text("No key needed.")
        else:
            status = Text("No key needed (save one if the address asks for it).")
        self.query_one("#ai-key-status", Static).update(status)
        self.query_one("#forget-key", Button).display = bool(saved and saved.strip())

    def _key_entered(self, key):
        if key is None:
            return
        try:
            self._keys.set(self._provider, key)
        except OSError as error:
            _log.warning("the %s key could not be saved: %s", self._provider, error)
            self._show_key(str(error))
        else:
            _log.info("a %s key was saved (in the system keyring)", self._provider)
            self._show_key()

    # Model

    def _pick_model(self):
        provider = PROVIDERS[self._provider]
        _, _, url = self.values
        try:
            connection = listing(provider.id, self._key(), url)
        except AiError as error:
            info = self.query_one("#ai-model-info", Static)
            info.update(Text(f"ERROR {error}", style="bold red"))
            return
        load = partial(self._fetch_models, connection)
        self.app.push_screen(ModelPicker(provider.name, load), self._model_picked)

    def _model_picked(self, model):
        if model is None:
            return
        self.query_one("#ai-model", Input).value = model.id
        self.query_one("#ai-model-info", Static).update(Text(describe(model)))

    # Buttons and Enter

    def on_button_pressed(self, event: Button.Pressed):
        event.stop()
        button = event.button.id
        if button == "set-key":
            name = PROVIDERS[self._provider].name
            self.app.push_screen(KeyDialog(name), self._key_entered)
        elif button == "forget-key":
            _log.info("the saved %s key was forgotten", self._provider)
            self._keys.delete(self._provider)
            self._show_key()
        elif button == "pick-model":
            self._pick_model()
        elif button == "send-chat":
            self._send()
        elif button == "clear-chat":
            self._clear()

    def on_input_submitted(self, event: Input.Submitted):
        # Enter in the chat box sends; in the other boxes it saves the page.
        if event.input.id == "chat-input":
            event.stop()
            self._send()

    # Test chat

    def _send(self):
        box = self.query_one("#chat-input", Input)
        message = box.value.strip()
        if not message or self._waiting:
            return
        provider_id, model, url = self.values
        box.value = ""
        self._add_line(Text.assemble(("YOU  ", "bold"), message))
        try:
            connection = connect(provider_id, model, self._key(), url)
        except AiError as error:
            self._failed(error, self._add_line(Text()), message, self._conversation)
            return
        conversation = [*self._history, {"role": "user", "content": message}]
        waiting = Text.assemble(("AI   ", "bold"), (f"waiting for {model}…", "dim"))
        self._waiting = True
        self._ask(connection, conversation, self._add_line(waiting), self._conversation)

    @work(thread=True, group="test-chat")
    def _ask(self, connection, conversation, line, conversation_id):
        try:
            reply = self._send_chat(connection, conversation)
        except Exception as error:  # noqa: BLE001 - a failing worker closes the app
            message = conversation[-1]["content"]
            self.app.call_from_thread(
                self._failed, error, line, message, conversation_id
            )
        else:
            self.app.call_from_thread(
                self._answered, reply, conversation, line, conversation_id
            )

    def _answered(self, reply, conversation, line, conversation_id):
        self._waiting = False
        if conversation_id != self._conversation:
            return  # CLEAR was pressed while waiting
        self._history = [*conversation, {"role": "assistant", "content": reply.text}]
        details = [reply.model]
        if reply.input_tokens is not None:
            details.append(f"{reply.input_tokens} in")
        if reply.output_tokens is not None:
            details.append(f"{reply.output_tokens} out")
        details.append(f"{reply.seconds:.1f} s")
        line.update(
            Text.assemble(
                ("AI   ", "bold"),
                reply.text,
                "\n",
                ("     " + " · ".join(details), "dim"),
            )
        )
        self._scroll_log()

    def _failed(self, error, line, message, conversation_id):
        self._waiting = False
        if conversation_id != self._conversation:
            return
        line.update(Text.assemble(("ERROR ", "bold red"), str(error)))
        box = self.query_one("#chat-input", Input)
        if not box.value:
            box.value = message  # ready to send again
        self._scroll_log()

    def _clear(self):
        self._history = []
        self._conversation += 1
        self.query_one("#chat-log", VerticalScroll).remove_children()

    def _add_line(self, text):
        line = Static(text, classes="chat-line")
        self.query_one("#chat-log", VerticalScroll).mount(line)
        self._scroll_log()
        return line

    def _scroll_log(self):
        self.query_one("#chat-log", VerticalScroll).scroll_end(animate=False)
