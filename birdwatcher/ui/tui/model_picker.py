"""
The model picker: lists a provider's models to choose from, with a filter.

Joshua Evans, 2026-11-18 (written with Claude Opus 5.5)
"""

from typing import ClassVar

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from birdwatcher.core.ai import AiError

THOUSAND, MILLION = 1_000, 1_000_000


class ModelPicker(ModalScreen):
    """
    Lists a provider's models (#model-list), loaded on a background thread,
    while #model-status says they are on the way; a failure shows its message
    there instead. Each option shows the model's id, its name, its price
    ("free", or dollars per million tokens in and out) and its context
    length, as far as the provider lists them.

    Typing in #model-filter keeps the models whose id or name contain every
    word typed (ignoring case). Choosing a model (Enter or a click on the
    list, or Enter in the filter for the highlighted or first match) closes
    the picker with its ModelInfo; Escape closes it with None.

    Args:
        provider_name (str): The provider, named while loading.
        load (Callable[[], list[ModelInfo]]): Fetches the models; called on a
            background thread; raises core.ai.AiError on failure.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, provider_name, load):
        super().__init__()
        self._provider_name = provider_name
        self._load = load
        self._models = []
        self._shown = []

    def compose(self) -> ComposeResult:
        with Vertical(id="model-picker") as picker:
            picker.border_title = Content("[ CHOOSE A MODEL ]")
            yield Input(
                placeholder="Filter: words in the name, e.g. free, claude, gemma",
                id="model-filter",
            )
            yield Static(
                Text(f"Asking {self._provider_name} for its models…"),
                id="model-status",
            )
            yield OptionList(id="model-list")

    def on_mount(self):
        self.query_one("#model-filter", Input).focus()
        self._fetch()

    @work(thread=True, exclusive=True)
    def _fetch(self):
        try:
            models = self._load()
        except AiError as error:
            self.app.call_from_thread(self._show_status, str(error))
        except Exception as error:  # noqa: BLE001 - a failing worker closes the app
            self.app.call_from_thread(self._show_status, f"ERROR {error}")
        else:
            self.app.call_from_thread(self._show_models, models)

    def _show_status(self, message):
        self.query_one("#model-status", Static).update(Text(message))

    def _show_models(self, models):
        self._models = list(models)
        count = len(self._models)
        self._show_status(f"{count} models from {self._provider_name}.")
        self._filter(self.query_one("#model-filter", Input).value)

    def on_input_changed(self, event: Input.Changed):
        event.stop()
        self._filter(event.value)

    def _filter(self, typed):
        words = typed.lower().split()
        self._shown = [
            model
            for model in self._models
            if all(word in f"{model.id} {model.name or ''}".lower() for word in words)
        ]
        listed = self.query_one("#model-list", OptionList)
        listed.clear_options()
        listed.add_options(
            Option(_prompt(model), id=str(index))
            for index, model in enumerate(self._shown)
        )
        if self._shown:
            listed.highlighted = 0

    def on_input_submitted(self, event: Input.Submitted):
        event.stop()
        listed = self.query_one("#model-list", OptionList)
        if self._shown:
            self.dismiss(self._shown[listed.highlighted or 0])

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        event.stop()
        self.dismiss(self._shown[int(event.option.id)])

    def action_cancel(self):
        self.dismiss(None)


def describe(model):
    """
    A model's name, price and context length in a few words.

    Args:
        model (ModelInfo): The model.

    Returns:
        str: For example "Free Models Router · free · 200K tokens", leaving
            out what the provider does not list ("" when it lists nothing).
    """
    parts = [model.name] if model.name else []
    price = _price(model)
    if price:
        parts.append(price)
    if model.context_length:
        parts.append(f"{_tokens(model.context_length)} tokens")
    return " · ".join(parts)


def _price(model):
    if model.input_price is None or model.output_price is None:
        return ""
    if model.input_price == 0 and model.output_price == 0:
        return "free"
    return f"${model.input_price:.2f} in / ${model.output_price:.2f} out per M"


def _tokens(count):
    if count >= MILLION:
        return f"{count / MILLION:.3g}M"
    if count >= THOUSAND:
        return f"{count // THOUSAND}K"
    return str(count)


def _prompt(model):
    prompt = Text(model.id, style="bold")
    details = describe(model)
    if details:
        prompt.append(f"   {details}", style="dim")
    return prompt
