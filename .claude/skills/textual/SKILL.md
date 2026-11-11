---
name: textual
description: Building and testing terminal apps with Textual (8.x) and Rich - headless pilot tests (keys, clicks, drags, window sizes), screenshots and theme galleries, traps that fail silently (square brackets read as markup, run_action is a coroutine, handlers running per class, lazy Tree lines, late theme signals, workers that close the app), retro styling in .tcss, layouts that follow the window, desktop integrations (editors, folder picker). Use for any work on a Textual app, its tests or its stylesheet.
---

# Textual apps

Measured on Textual 8.2.8 and Rich 15 (Python 3.12, Windows Terminal), building Birdwatcher. Each trap below failed silently or confusingly at least once; the fix shown is the one that held.

## Testing headless

Drive the real app with `run_test` and its pilot. No pytest-asyncio is needed: wrap the async body in `asyncio.run` inside an ordinary test.

```python
def drive(app, steps, size=(140, 40)):
    async def main():
        async with app.run_test(size=size) as pilot:
            await settle(app, pilot)
            await steps(app, pilot)

    asyncio.run(main())


async def settle(app, pilot):
    # After anything that starts a thread worker (loading, re-checking).
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()
```

- Keys: `await pilot.press("n", "enter", "ctrl+o")`. Clicks: `await pilot.click("#save")` or `pilot.click(WidgetClass, offset=(x, y))`.
- Window size per test with `run_test(size=...)`; mid-test with `await pilot.resize_terminal(w, h)`.
- Read what a `Static` shows through its public `.content`, rendered by Rich: `Console(file=io.StringIO(), width=120, color_system=None).print(widget.content)`. Unwrapped long lines are cropped at that width, so render wide to check one.
- Whether a widget is on screen: `widget.display` (False when CSS says `display: none`).
- **Drags: aim in screen coordinates.** `pilot.mouse_up(widget, offset)` first moves the pointer to the widget, which has moved during the drag, so the offset counts twice:

```python
start = app.query_one(Divider).region.x
destination = (start + columns, 0)
await pilot.mouse_down(Divider)
await pilot.hover(None, offset=destination)
await pilot.mouse_up(None, offset=destination)
```

- Pass every desktop side effect into the app as a function (open an editor, a browser, a folder picker, a file browser, the system's dark-mode setting), so tests use fakes that record calls, and the real ones are checked by hand.
- If the environment sets `NO_COLOR`, Textual renders in greyscale (the app gains a `nocolor` pseudo-class). Clear it, and set `COLORTERM=truecolor`, before taking screenshots meant to show color.

## Screenshots and theme galleries

Inside `run_test`, set a theme and save an SVG; a small HTML page of them compares looks side by side.

```python
for theme in sorted(app.available_themes):  # 21 built-in themes in 8.x
    app.theme = theme
    await pilot.pause()
    app.save_screenshot(f"{theme}.svg", path=str(out_dir))
```

Run the real app on real data with a throwaway settings file, so the app's real settings stay untouched. To check a screenshot's content, search the SVG text: spaces are `&#160;`, and each differently styled run is its own element (`[`, `X`, `]` and ` FIXED 0` are four), so search for the pieces.

## Traps that fail silently

- **Square brackets in widget text are markup.** `Button("[F] FIX")` shows " FIX"; `border_title = "[ FINDINGS ]"` shows nothing at all. Pass literal text as `textual.content.Content("[F] FIX")`. Text that comes from files or people, shown with Rich, goes into `rich.text.Text`, never markup.
- **`Screen.run_action` is a coroutine.** Called from a button handler without `await`, it never runs (only a "coroutine was never awaited" warning). Call the `action_x()` method directly.
- **Event handlers run for every class in the hierarchy.** A subclass's `_on_click` runs, then the parent's runs too. Call `event.prevent_default()` in the override to stop the parent's.
- **`watch_x` methods are the opposite: a subclass's replaces the parent's.** Call `super().watch_x()`. (`Checkbox.watch_value` is what posts `Changed`.)
- **A thread worker that raises closes the app.** Catch inside the worker and hand the error to the UI:

```python
@work(thread=True, exclusive=True)
def _check_in_background(self, folder):
    try:
        run = self._check(folder)
    except Exception as error:
        self.app.call_from_thread(self._show_error, error)
    else:
        self.app.call_from_thread(self._show, run)
```

- **A `Widget` without `render()` shows its own name and CSS classes as text.** Give every custom widget a `render()` (`""` for nothing).
- **`Tree` selects on every click** (`DataTable` selects only when the clicked row was already highlighted). To get "first click highlights, second click opens" on a tree:

```python
class FindingsTree(Tree):
    async def _on_click(self, event):
        event.prevent_default()  # or Tree's own handler runs as well
        async with self.lock:
            line = event.style.meta.get("line")
            node = None if line is None else self.get_node_at_line(line)
            if node is None:
                return
            if node.allow_expand:  # branches fold at once
                self.cursor_line = line
                node.toggle()
            elif line == self.cursor_line:
                self.post_message(Tree.NodeSelected(node))
            else:
                self.cursor_line = line
```

- **Tree line numbers are computed lazily.** Right after rebuilding a tree, `node.line` is -1 and `move_cursor(node)` goes nowhere. Read `tree.last_line` first to force the computation.
- **`theme_changed_signal` publishes through `call_next`, after the change.** A "this change is mine" flag is already reset when it arrives. Remember the theme name the app set itself and treat any other name as the user's (for example from the command palette):

```python
def _apply_theme(self, name):
    self._own_theme = name
    self.theme = name

def _theme_changed(self, theme):       # subscribed in on_mount:
    if theme.name == self._own_theme:  # self.theme_changed_signal.subscribe(self, ...)
        return
    self._own_theme = theme.name
    ...save theme.name as the user's choice...
```

- **`Checkbox` always draws an X and shows on/off by color alone.** To show the state in characters:

```python
class StatusChip(Checkbox):
    BUTTON_LEFT, BUTTON_RIGHT = "[", "]"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.BUTTON_INNER = "X" if self.value else " "

    def watch_value(self):
        super().watch_value()  # posts Changed
        self.BUTTON_INNER = "X" if self.value else " "
        self.refresh()
```

- **A scrolling container with `width: auto` collapses to nothing** (`VerticalScroll` does not size to its content), so a dialog built on one shows as an empty box while tests reading the widget's text still pass. Give it a width (`width: 80; max-width: 95%`), and assert on `widget.region` in a test when on-screen size matters.
- **`size.width` of a scrolling widget includes its vertical scrollbar**, which is drawn over the last columns. To fit text to the visible width (e.g. a `Tree.render_label` override that right-aligns a marker), subtract `styles.scrollbar_size_vertical` always, whether or not the bar shows, so lines don't shift when it appears.
- **Rich wraps at a no-break space too.** To keep a `-`/`+` sign beside text that may wrap, put the sign in its own column of a `Table.grid` rather than joining it with `\N{NO-BREAK SPACE}`; give the text column `overflow="fold"` so a long unbroken word (a URL, an anchor) breaks across lines instead of ending in "…".
- `BINDINGS` (and other mutable class attributes) need `ClassVar[list[BindingType]]` for Ruff's RUF012.
- `widget.size` excludes the border, `outer_size` includes it, and `styles.width` sets the outer width; mixing them drifts by a column.

## Bindings and the footer

`check_action` returning False hides a binding from the footer and stops its key, so the footer can list only what applies to the current selection. Call `self.refresh_bindings()` whenever the selection changes.

```python
def check_action(self, action, parameters):
    if action == "fix":
        row = self._current()
        return row is not None and row.finding.fix is not None
    return True
```

## Styling (.tcss)

- Styles live in a `.tcss` file named by `CSS_PATH`, using theme variables (`$accent`, `$error`, `$warning`, `$surface`, `$background`) so every theme works.
- **Live reload without extra packages:** run with `TEXTUAL_DEBUG=1`; the app reloads the stylesheet on save. Debug mode also writes **every key and mouse event to `keys.log` in the current folder**: git-ignore it. (`textual run --dev` needs the separate `textual-dev` package.)
- Double-line frames with titles in the border:

```css
#pane {
    border: double $accent;
    border-title-align: left;
    border-title-style: bold;
    border-title-color: $accent;
}
```

  Set the title in code as `Content("[ FINDINGS ]")` (see the markup trap). Per-side borders (`border-right: none`) let two framed panes share one wall drawn by a widget between them (`╦`, `║`..., `╩`).
- One-line flat buttons: `Button { border: none; height: 1; min-width: 0; padding: 0 1; }`.
- Tabs on one line with a solid active tab: hide the underline (`#tabs Underline { display: none; }`, `#tabs { height: 1; }`) and style `#tabs Tab.-active`.
- Textual 8 has a `pointer` property (`pointer: ew-resize;`, sent as OSC 22). Windows Terminal ignores it; kitty, Ghostty and WezTerm show it.
- There is no `text-transform`: write capitals in the strings themselves.

## Layouts that follow the window

Toggle classes on the screen in `on_resize`, and let the stylesheet show or hide panes:

```python
def on_resize(self, event):
    narrow = self.size.width < NARROW_WIDTH
    self.set_class(narrow, "-narrow")
    self.set_class(self._zoomed, "-zoomed")
    # A width set from code outranks the stylesheet, so reset it per layout.
    self.query_one("#list-pane").styles.width = "1fr" if narrow else f"{self._split}%"
```

```css
MyScreen.-narrow #detail { display: none; }
MyScreen.-zoomed #list-pane { display: none; }
MyScreen.-zoomed #detail { display: block; }   /* after the -narrow rule, so it wins */
```

No built-in splitter exists: a one-column widget that calls `capture_mouse()` on mouse down, sets the left pane's `styles.width` from `event.screen_x` on mouse move, and `release_mouse()` on mouse up does it (clamp both panes to a minimum width).

## Widgets that work as expected

`ModalScreen` with `dismiss(result)` and `push_screen(screen, callback)`; `OptionList` (an `OptionSelected` event per choice); `RadioSet` (`pressed_button`; disabled buttons cannot be chosen); `Select(options, value=..., allow_blank=False)` with `Select.Changed`; `Tabs` with `Tabs.TabActivated` (set `tabs.active = "tab-id"` to switch from code); `HorizontalScroll` around a `Static` with `width: auto` and Rich `Syntax(..., word_wrap=False)` for source lines that scroll sideways instead of wrapping.

## Desktop integrations

- **Native folder picker from a terminal app:** `tkinter.filedialog.askdirectory`, on the main thread (macOS requires it; the terminal app pauses while the picker is open), with a hidden, topmost Tk root so the picker opens in front of the terminal. uv's Python builds include Tk 8.6.

```python
import tkinter
from tkinter import filedialog

root = tkinter.Tk()
try:
    root.withdraw()
    root.attributes("-topmost", True)
    chosen = filedialog.askdirectory(parent=root, mustexist=True)
finally:
    root.destroy()
folder = Path(chosen) if chosen else None  # "" or () when cancelled
```

- **System dark mode:** Windows `HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize\AppsUseLightTheme` (0 = dark); macOS `defaults read -g AppleInterfaceStyle` prints "Dark" (fails in light mode); GNOME `gsettings get org.gnome.desktop.interface color-scheme`. This is the system's setting, not the terminal's colors.
- **Opening files:** VS Code opens at a line with `code --goto path:line` (the `code` command must be on PATH; on a Mac, VS Code's "Install 'code' command in PATH"). Typora cannot open at a line; on Windows it registers an `App Paths` entry (`HKCU` or `HKLM\Software\Microsoft\Windows\CurrentVersion\App Paths\Typora.exe`), on a Mac `open -a Typora file`. The system default app: `os.startfile` on Windows, `open` on a Mac, `xdg-open` elsewhere (these also show a folder in the file browser).
