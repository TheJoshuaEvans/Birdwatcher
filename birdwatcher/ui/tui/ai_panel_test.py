"""
Contract tests for the setup page's AI MODEL tab (birdwatcher.ui.tui.ai_panel,
its dialogs, and how the app saves it), driven headless through the app.

Joshua Evans, 2026-11-18 (written with Claude Opus 5.5)
"""

import sys

import pytest
from textual.widgets import Input, OptionList, RadioButton, Static

from birdwatcher.core.ai import CUSTOM, GEMINI, OPENROUTER, AiError, ModelInfo, Reply
from birdwatcher.core.config import Config, load_config, save_config
from birdwatcher.ui.tui.app_test import (
    FakeChecker,
    drive,
    is_visible,
    make_app,
    make_course,
    on_setup,
    press,
    render_text,
    settle,
)
from birdwatcher.ui.tui.key_dialog import KeyDialog
from birdwatcher.ui.tui.model_picker import ModelPicker
from birdwatcher.ui.tui.reset import ResetDialog

SECRET = "sk-or-v1-secret-test-key"
ENV = {"OPENROUTER_API_KEY": SECRET}
MODELS = [
    ModelInfo(
        "anthropic/claude-opus-5.5", "Anthropic: Claude Opus 5.5", 1_000_000, 4.0, 20.0
    ),
    ModelInfo(
        "google/gemma-4-31b-it:free", "Google: Gemma 4 31B (free)", 262_144, 0.0, 0.0
    ),
    ModelInfo("openrouter/free", "Free Models Router", 200_000, 0.0, 0.0),
]


class FakeChat:
    """Stands in for core.ai.chat: answers with each outcome in turn (the last
    repeats; an exception is raised) and records each connection and a copy
    of each conversation."""

    def __init__(self, *outcomes):
        self.outcomes = outcomes or (
            Reply("Paris", "google/gemma-4-31b-it:free", 12, 3, 1.25),
        )
        self.calls = []

    def __call__(self, connection, messages):
        self.calls.append((connection, [dict(message) for message in messages]))
        outcome = self.outcomes[min(len(self.calls), len(self.outcomes)) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeModels:
    """Stands in for core.ai.list_models: returns `outcome` (or raises it) and
    records the connections asked about."""

    def __init__(self, outcome=MODELS):
        self.outcome = outcome
        self.connections = []

    def __call__(self, connection):
        self.connections.append(connection)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return list(self.outcome)


def ai_app(tmp_path, config=None, **fakes):
    """An app with a usable course saved (with `config`'s AI settings, when
    given) and the fakes passed on to make_app."""
    course = make_course(tmp_path / "course")
    app, config_path = make_app(tmp_path, FakeChecker(), course, **fakes)
    if config is not None:
        save_config(config_path, Config(course_dir=course, recent=(course,), **config))
    return app, config_path, course


async def open_ai_tab(app, pilot):
    if not on_setup(app):
        await press(app, pilot, "s")
    await pilot.click("#tab-ai")
    await settle(app, pilot)


def text(app, selector):
    return render_text(app.screen.query_one(selector, Static).content)


def chat_log(app):
    return "".join(
        render_text(line.content) for line in app.screen.query("#chat-log Static")
    )


def everything_shown(app):
    return "".join(render_text(widget.content) for widget in app.screen.query(Static))


async def send(app, pilot, message):
    box = app.screen.query_one("#chat-input", Input)
    box.value = message
    box.focus()
    await press(app, pilot, "enter")


# Tabs


def test_setup_has_a_course_tab_and_an_ai_model_tab(tmp_path):
    app, _, _ = ai_app(tmp_path)

    async def steps(app, pilot):
        await press(app, pilot, "s")
        assert is_visible(app, "#setup")
        assert not is_visible(app, "#setup-ai")
        await open_ai_tab(app, pilot)
        assert is_visible(app, "#setup-ai")
        assert not is_visible(app, "#setup")
        await pilot.click("#tab-course")
        await settle(app, pilot)
        assert is_visible(app, "#setup")

    drive(app, steps)


def test_the_free_router_is_shown_with_its_warning(tmp_path):
    app, _, _ = ai_app(tmp_path)  # the default: openrouter/free

    async def steps(app, pilot):
        await open_ai_tab(app, pilot)
        assert "differ" in text(app, "#ai-model-warning")
        app.screen.query_one("#ai-model", Input).value = "google/gemma-4-31b-it:free"
        await settle(app, pilot)
        assert not is_visible(app, "#ai-model-warning")

    drive(app, steps)


def test_the_saved_provider_and_model_are_filled_in(tmp_path):
    config = {"ai_provider": GEMINI, "ai_model": "gemini-flash-latest"}
    app, _, _ = ai_app(tmp_path, config)

    async def steps(app, pilot):
        await open_ai_tab(app, pilot)
        assert app.screen.query_one(f"#provider-{GEMINI}", RadioButton).value
        assert app.screen.query_one("#ai-model", Input).value == "gemini-flash-latest"

    drive(app, steps)


# The key


def test_the_status_names_the_environment_variable_and_never_shows_the_key(tmp_path):
    app, _, _ = ai_app(tmp_path, environ=ENV)

    async def steps(app, pilot):
        await open_ai_tab(app, pilot)
        assert "OPENROUTER_API_KEY" in text(app, "#ai-key-status")
        assert not is_visible(app, "#forget-key")
        assert SECRET not in everything_shown(app)

    drive(app, steps)


def test_without_a_key_the_status_says_how_to_add_one(tmp_path):
    app, _, _ = ai_app(tmp_path)

    async def steps(app, pilot):
        await open_ai_tab(app, pilot)
        status = text(app, "#ai-key-status")
        assert "No key" in status and "OPENROUTER_API_KEY" in status
        await pilot.click("#provider-local")
        await settle(app, pilot)
        assert "No key needed" in text(app, "#ai-key-status")

    drive(app, steps)


def test_set_key_saves_it_in_the_key_store(tmp_path):
    keys = {}
    app, _, _ = ai_app(tmp_path, keys=keys)

    async def steps(app, pilot):
        await open_ai_tab(app, pilot)
        await pilot.click("#set-key")
        await settle(app, pilot)
        assert isinstance(app.screen, KeyDialog)
        box = app.screen.query_one("#key-input", Input)
        assert box.password
        assert "keyring" in text(app, "#key-text")
        box.value = f"  {SECRET} "
        box.focus()
        await press(app, pilot, "enter")
        assert keys == {OPENROUTER: SECRET}
        assert "saved in Birdwatcher" in text(app, "#ai-key-status")
        assert is_visible(app, "#forget-key")
        assert SECRET not in everything_shown(app)

    drive(app, steps)


def test_cancelling_set_key_saves_nothing(tmp_path):
    keys = {}
    app, _, _ = ai_app(tmp_path, keys=keys)

    async def steps(app, pilot):
        await open_ai_tab(app, pilot)
        await pilot.click("#set-key")
        await settle(app, pilot)
        app.screen.query_one("#key-input", Input).value = SECRET
        await press(app, pilot, "escape")
        assert keys == {}
        assert on_setup(app)

    drive(app, steps)


def test_a_saved_key_wins_and_forgetting_it_falls_back(tmp_path):
    keys = {OPENROUTER: "saved-key"}
    app, _, _ = ai_app(tmp_path, keys=keys, environ=ENV)

    async def steps(app, pilot):
        await open_ai_tab(app, pilot)
        assert "saved in Birdwatcher" in text(app, "#ai-key-status")
        await pilot.click("#forget-key")
        await settle(app, pilot)
        assert keys == {}
        assert "OPENROUTER_API_KEY" in text(app, "#ai-key-status")
        assert not is_visible(app, "#forget-key")

    drive(app, steps)


# Provider and model


def test_the_custom_provider_shows_its_address_box(tmp_path):
    app, _, _ = ai_app(tmp_path)

    async def steps(app, pilot):
        await open_ai_tab(app, pilot)
        assert not is_visible(app, "#ai-url")
        await pilot.click(f"#provider-{CUSTOM}")
        await settle(app, pilot)
        assert is_visible(app, "#ai-url")

    drive(app, steps)


def test_switching_providers_puts_each_ones_model_back(tmp_path):
    app, _, _ = ai_app(tmp_path)

    async def steps(app, pilot):
        await open_ai_tab(app, pilot)
        model = app.screen.query_one("#ai-model", Input)
        assert model.value == "openrouter/free"
        model.value = "anthropic/claude-opus-5.5"
        await pilot.click(f"#provider-{GEMINI}")
        await settle(app, pilot)
        assert model.value == ""  # Gemini has no default model
        await pilot.click(f"#provider-{OPENROUTER}")
        await settle(app, pilot)
        assert model.value == "anthropic/claude-opus-5.5"

    drive(app, steps)


def test_pick_lists_the_models_and_fills_in_the_choice(tmp_path):
    models = FakeModels()
    app, _, _ = ai_app(tmp_path, environ=ENV, fetch_models=models)

    async def steps(app, pilot):
        await open_ai_tab(app, pilot)
        await pilot.click("#pick-model")
        await settle(app, pilot)
        assert isinstance(app.screen, ModelPicker)
        (connection,) = models.connections
        assert connection.provider.id == OPENROUTER
        assert connection.key.source == "OPENROUTER_API_KEY"
        listed = app.screen.query_one("#model-list", OptionList)
        assert listed.option_count == len(MODELS)
        options = "".join(
            render_text(listed.get_option_at_index(i).prompt) for i in range(3)
        )
        assert "free" in options and "$4.00" in options and "1M" in options
        box = app.screen.query_one("#model-filter", Input)
        box.value = "OPUS anthropic"
        await settle(app, pilot)
        assert listed.option_count == 1
        box.focus()
        await press(app, pilot, "enter")
        assert on_setup(app)
        model = app.screen.query_one("#ai-model", Input).value
        assert model == "anthropic/claude-opus-5.5"
        info = text(app, "#ai-model-info")
        assert "Claude Opus 5.5" in info and "$4.00" in info

    drive(app, steps)


def test_a_failed_model_list_is_shown_in_the_picker(tmp_path):
    models = FakeModels(AiError("OpenRouter is down for maintenance."))
    app, _, _ = ai_app(tmp_path, fetch_models=models)

    async def steps(app, pilot):
        await open_ai_tab(app, pilot)
        await pilot.click("#pick-model")
        await settle(app, pilot)
        assert "down for maintenance" in text(app, "#model-status")
        await press(app, pilot, "escape")
        assert app.screen.query_one("#ai-model", Input).value == "openrouter/free"

    drive(app, steps)


# Test chat


def test_the_chat_sends_the_conversation_and_shows_the_answer(tmp_path):
    first = Reply("Paris.", "google/gemma-4-31b-it:free", 12, 3, 1.25)
    second = Reply("Berlin.", "google/gemma-4-31b-it:free", 20, 3, 0.5)
    chat = FakeChat(first, second)
    app, _, _ = ai_app(tmp_path, environ=ENV, send_chat=chat)

    async def steps(app, pilot):
        await open_ai_tab(app, pilot)
        await send(app, pilot, "Capital of France?")
        assert on_setup(app)  # Enter in the chat box sends; it does not save
        connection, messages = chat.calls[0]
        assert (connection.provider.id, connection.model) == (
            OPENROUTER,
            "openrouter/free",
        )
        assert connection.key.source == "OPENROUTER_API_KEY"
        assert messages == [{"role": "user", "content": "Capital of France?"}]
        log = chat_log(app)
        for shown in (
            "YOU",
            "Capital of France?",
            "AI",
            "Paris.",
            "gemma-4-31b-it",
            "12 in",
            "3 out",
        ):
            assert shown in log
        await send(app, pilot, "And Germany?")
        assert chat.calls[1][1] == [
            {"role": "user", "content": "Capital of France?"},
            {"role": "assistant", "content": "Paris."},
            {"role": "user", "content": "And Germany?"},
        ]
        assert "Berlin." in chat_log(app)
        assert app.screen.query_one("#chat-input", Input).value == ""

    drive(app, steps)


def test_a_failed_message_is_shown_and_left_out_of_the_conversation(tmp_path):
    chat = FakeChat(
        AiError("OpenRouter limited the rate of requests."),
        Reply("Hi.", "m", 1, 1, 0.1),
    )
    app, _, _ = ai_app(tmp_path, environ=ENV, send_chat=chat)

    async def steps(app, pilot):
        await open_ai_tab(app, pilot)
        await send(app, pilot, "First try")
        log = chat_log(app)
        assert "ERROR" in log and "limited the rate" in log
        await send(app, pilot, "Second try")
        assert chat.calls[1][1] == [{"role": "user", "content": "Second try"}]

    drive(app, steps)


def test_the_chat_without_a_key_explains_and_sends_nothing(tmp_path):
    chat = FakeChat()
    app, _, _ = ai_app(tmp_path, send_chat=chat)

    async def steps(app, pilot):
        await open_ai_tab(app, pilot)
        await send(app, pilot, "Hello?")
        log = chat_log(app)
        assert "ERROR" in log and "OPENROUTER_API_KEY" in log
        assert chat.calls == []

    drive(app, steps)


def test_clear_starts_a_new_conversation(tmp_path):
    chat = FakeChat()
    app, _, _ = ai_app(tmp_path, environ=ENV, send_chat=chat)

    async def steps(app, pilot):
        await open_ai_tab(app, pilot)
        await send(app, pilot, "One")
        await pilot.click("#clear-chat")
        await settle(app, pilot)
        assert "One" not in chat_log(app)
        await send(app, pilot, "Two")
        assert chat.calls[-1][1] == [{"role": "user", "content": "Two"}]

    drive(app, steps)


# Saving


def test_saving_from_the_ai_tab_saves_the_ai_settings(tmp_path):
    app, config_path, course = ai_app(tmp_path)

    async def steps(app, pilot):
        await open_ai_tab(app, pilot)
        await pilot.click(f"#provider-{CUSTOM}")
        await settle(app, pilot)
        app.screen.query_one("#ai-url", Input).value = " http://localhost:1234/v1 "
        app.screen.query_one("#ai-model", Input).value = " qwen3:8b "
        await pilot.click("#save-ai")
        await settle(app, pilot)
        assert not on_setup(app)
        saved = load_config(config_path)
        assert (saved.ai_provider, saved.ai_model, saved.ai_url) == (
            CUSTOM,
            "qwen3:8b",
            "http://localhost:1234/v1",
        )
        assert saved.course_dir == course

    drive(app, steps)


def test_saving_from_the_ai_tab_without_a_course_shows_the_course_tab(tmp_path):
    app, _ = make_app(tmp_path, FakeChecker())  # first run: no course yet

    async def steps(app, pilot):
        await open_ai_tab(app, pilot)
        await pilot.click("#save-ai")
        await settle(app, pilot)
        assert on_setup(app)
        assert is_visible(app, "#setup")
        assert "path" in text(app, "#setup-error")

    drive(app, steps)


def test_escape_forgets_unsaved_ai_changes(tmp_path):
    app, config_path, _ = ai_app(tmp_path)
    before = load_config(config_path)

    async def steps(app, pilot):
        await open_ai_tab(app, pilot)
        app.screen.query_one("#ai-model", Input).value = "something/else"
        app.screen.query_one("#tab-ai").focus()
        await press(app, pilot, "escape")
        assert not on_setup(app)
        assert load_config(config_path) == before

    drive(app, steps)


def test_reset_everything_forgets_the_saved_keys(tmp_path):
    keys = {OPENROUTER: "one", GEMINI: "two"}
    app, _, _ = ai_app(tmp_path, keys=keys)

    async def steps(app, pilot):
        await press(app, pilot, "s")
        await pilot.click("#reset")
        await settle(app, pilot)
        assert isinstance(app.screen, ResetDialog)
        assert "API keys" in render_text(
            app.screen.query_one("#reset-text", Static).content
        )
        await press(app, pilot, "enter")
        assert keys == {}

    drive(app, steps)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
