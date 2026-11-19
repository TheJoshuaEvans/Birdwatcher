"""
Contract tests for the setup page's keyboard use (birdwatcher.ui.tui.setup and
its model picker), driven headless through the app. The page's other behavior
is covered by app_test.py and ai_panel_test.py.

Joshua Evans, 2026-11-19 (written with Claude Opus 5.5)
"""

import sys

import pytest
from textual.widgets import Input, OptionList, Tabs

from birdwatcher.core.ai import ModelInfo
from birdwatcher.core.config import load_config
from birdwatcher.ui.tui.ai_panel_test import ai_app, open_ai_tab
from birdwatcher.ui.tui.app_test import (
    FakeChecker,
    FakeChooser,
    drive,
    is_visible,
    make_app,
    on_setup,
    press,
    settle,
)
from birdwatcher.ui.tui.model_picker import ModelPicker

MODELS = [
    ModelInfo("a/first", "First"),
    ModelInfo("b/second", "Second"),
    ModelInfo("c/third", "Third"),
]


def footer_keys(app):
    """The descriptions of the keys the footer shows now."""
    return {
        active.binding.description
        for active in app.screen.active_bindings.values()
        if active.enabled and active.binding.show
    }


def focus(app, selector):
    app.screen.query_one(selector).focus()


# Switching tabs


def test_ctrl_t_switches_tabs_even_from_a_text_box(tmp_path):
    app, _, _ = ai_app(tmp_path)

    async def steps(app, pilot):
        await press(app, pilot, "s")
        focus(app, "#course-dir")
        await press(app, pilot, "ctrl+t")
        assert is_visible(app, "#setup-ai")
        assert not is_visible(app, "#setup")
        assert isinstance(app.focused, Tabs)  # not left on a hidden box
        focus(app, "#chat-input")
        await press(app, pilot, "ctrl+t")
        assert is_visible(app, "#setup")
        assert "Switch tab" in footer_keys(app)

    drive(app, steps)


def test_browse_is_offered_on_the_course_tab_only(tmp_path):
    chooser = FakeChooser()
    app, _ = make_app(tmp_path, FakeChecker(), chooser=chooser)

    async def steps(app, pilot):
        assert "Browse" in footer_keys(app)
        await open_ai_tab(app, pilot)
        assert "Browse" not in footer_keys(app)
        await press(app, pilot, "ctrl+o")
        assert chooser.starts == []  # the folder picker did not open

    drive(app, steps)


# Saving


@pytest.mark.parametrize("box", ["#ai-model", "#chat-input"])
def test_ctrl_s_saves_from_anywhere_on_the_page(tmp_path, box):
    app, config_path, _ = ai_app(tmp_path)

    async def steps(app, pilot):
        await open_ai_tab(app, pilot)
        app.screen.query_one("#ai-model", Input).value = "a/first"
        focus(app, box)
        assert "Save" in footer_keys(app)
        await press(app, pilot, "ctrl+s")
        assert not on_setup(app)
        assert load_config(config_path).ai_model == "a/first"

    drive(app, steps)


def test_ctrl_s_without_a_usable_course_shows_why(tmp_path):
    app, _ = make_app(tmp_path, FakeChecker())  # first run: no course yet

    async def steps(app, pilot):
        await open_ai_tab(app, pilot)
        await press(app, pilot, "ctrl+s")
        assert on_setup(app)
        assert is_visible(app, "#setup")

    drive(app, steps)


# Escape


def test_escape_in_a_text_box_leaves_the_box_then_goes_back(tmp_path):
    app, config_path, _ = ai_app(tmp_path)
    before = load_config(config_path)

    async def steps(app, pilot):
        await open_ai_tab(app, pilot)
        app.screen.query_one("#ai-model", Input).value = "typed/but-not-saved"
        focus(app, "#chat-input")
        await press(app, pilot, "escape")
        assert on_setup(app)  # nothing typed is lost yet
        assert isinstance(app.focused, Tabs)
        assert app.screen.query_one("#ai-model", Input).value == "typed/but-not-saved"
        await press(app, pilot, "escape")
        assert not on_setup(app)
        assert load_config(config_path) == before

    drive(app, steps)


def test_escape_on_a_first_run_leaves_the_box_but_stays(tmp_path):
    app, _ = make_app(tmp_path, FakeChecker())

    async def steps(app, pilot):
        focus(app, "#course-dir")
        await press(app, pilot, "escape")
        assert isinstance(app.focused, Tabs)
        await press(app, pilot, "escape")
        assert on_setup(app)  # a first run cannot be cancelled

    drive(app, steps)


# The model picker


@pytest.mark.parametrize(
    ("keys", "chosen"),
    [
        (["down", "enter"], "b/second"),
        (["down", "down", "up", "enter"], "b/second"),
        (["pagedown", "enter"], "c/third"),
        (["pagedown", "pageup", "enter"], "a/first"),
    ],
)
def test_arrows_in_the_filter_move_through_the_models(tmp_path, keys, chosen):
    app, _, _ = ai_app(tmp_path, fetch_models=lambda connection: MODELS)

    async def steps(app, pilot):
        await open_ai_tab(app, pilot)
        await pilot.click("#pick-model")
        await settle(app, pilot)
        assert isinstance(app.screen, ModelPicker)
        assert isinstance(app.focused, Input)  # typing goes to the filter
        await press(app, pilot, *keys)
        assert app.screen.query_one("#ai-model", Input).value == chosen

    drive(app, steps)


def test_the_filter_keeps_focus_while_moving(tmp_path):
    app, _, _ = ai_app(tmp_path, fetch_models=lambda connection: MODELS)

    async def steps(app, pilot):
        await open_ai_tab(app, pilot)
        await pilot.click("#pick-model")
        await settle(app, pilot)
        await press(app, pilot, "down")
        assert app.focused is app.screen.query_one("#model-filter", Input)
        assert app.screen.query_one("#model-list", OptionList).highlighted == 1

    drive(app, steps)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
