# Birdwatcher

Watches Brian Bird's course materials at Lane Community College (CS 212, AI Programming 1, and his other courses) for consistency problems and blind spots.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)

## What it does

Birdwatcher runs static checks over a local clone of one of Brian Bird's course repositories, such as [lcc-cit/CS212-CourseMaterials](https://github.com/lcc-cit/CS212-CourseMaterials), and shows each problem it finds in an interactive terminal app: open the exact file and line in an editor, fix it, and re-run the checks to confirm the fix.

A course's site is published by GitHub Pages either from its `docs/` folder (CS 212, CIS 195, CS 112) or from the repository's top folder (CS 133JS, CS 233JS, CS 246, CS 297); Birdwatcher checks `docs/` when there is one, and the whole repository otherwise, leaving out what Jekyll leaves out (`node_modules/`, `vendor/`, folders starting with `_` or `.`) and saved copies of other sites' pages (a page saved with its `Page_files/` or `Page.fld/` folder).

The course repository already checks that its links resolve, using [lychee](https://lychee.cli.rs/) in GitHub Actions. Birdwatcher looks for what a link checker can't see: links to sections that don't exist, files left over from renumbering, accessibility problems, and code that breaks the course's own style rules.

**Status:** early development, as the CS 212 Lab 6 project. It grows into the term project: Lab 7 adds analysis by a large language model, and the term project adds simulated students. Downloading, caching, the app and the first check work; the other checks below are being built.

## Running Birdwatcher

With [uv](https://docs.astral.sh/uv/) installed, one command runs Birdwatcher straight from this repository, with nothing to download or install by hand:

```powershell
uvx --from git+https://github.com/TheJoshuaEvans/Birdwatcher birdwatcher
```

Add `@` and a tag, branch or commit to run that version instead of the latest, for example `...Birdwatcher@main` or `...Birdwatcher@d4e11d8`. Anything after `birdwatcher` is passed on, so `... birdwatcher check --list-checks` works too. To keep it installed as a `birdwatcher` command, use `uv tool install git+https://github.com/TheJoshuaEvans/Birdwatcher`.

## Setup for development

Requires [uv](https://docs.astral.sh/uv/), which installs Python 3.12 itself.

```powershell
uv sync
uv run pytest
```

## Usage

```powershell
uv run birdwatcher                    # open the app
uv run birdwatcher check              # check once and print a summary
uv run birdwatcher check --verbose    # ... with progress and every finding
uv run birdwatcher check --course-dir C:\path\to\CS212-CourseMaterials
uv run birdwatcher check --list-checks
```

The first time the app opens, it asks for the folder of your local clone of a course repository (the folder that holds its pages, in `docs/` or at the top) and remembers it. Type or paste the path, or press **Browse…** (Ctrl+O) to pick it in your system's folder picker. The setup page (`s`) also lists your recent course folders, so switching between courses is one click, and lets you choose the editor that opens files and the color theme (by default, light or dark to match your system; any theme picked with Ctrl+P is remembered too). `birdwatcher check` uses the same folder unless `--course-dir` names another. To look around without a clone of your own, press **Try the demo** on the setup page: Birdwatcher downloads the CS 212 course materials (about 34 MB) into its cache folder, with the course's word list, and opens them with DEMO in the title. The demo is a fixed snapshot of the course (one commit, from November 2026), so it keeps its findings however the real course improves. It is never saved as your course; later demos open the downloaded copy at once, and **Refresh demo** downloads a clean copy again (after trying out fixes in it, say). On the setup page, `q` (outside the path box) or Escape goes back to the course; on a first run, with no course yet, `q` quits. **Reset everything…** on the setup page forgets all of that, along with the fixed and ignored findings and the saved link answers, after asking, and starts again as on a first run; course folders are not touched.

Findings appear as each check finishes, so the quick checks show at once while a slow one is still running. When checking again, each check's previous findings stay in the list until its new results arrive.

In the app, mouse and keyboard both work. The bottom bar shows the keys for what is selected; `?` lists every key, marking the ones that do not apply right now:

| Do | To |
|---|---|
| Click a finding, or `n` / `p` (next / previous finding) | Show it: check, location, message, and the source lines around it |
| Click it again, or press Enter or `o` | Open the file at that line in your editor |
| Click a branch, or the arrow keys and Enter | Fold or unfold it (folded branches stay folded when the checks run again) |
| `-` / `+` | Fold or unfold one level of branches at a time: from everything open, `-` folds the deepest level, down to one line per check (or the top folder); `+` opens the list back up a level at a time |
| `z`, then `z` or Escape to go back | Show the finding's detail filling the window (in a window narrower than 120 columns, the detail is shown this way instead of beside the list) |
| Drag the bar between the panes | Change the split; Birdwatcher remembers it |
| The **Check / Folder** tabs, or `g` | Group the findings by check or by folder |
| The **SHOW** chips, or `1` / `2` / `3` | Show or hide errors, warnings and info (each chip shows how many are open; Birdwatcher remembers the choice, and starts with errors and warnings) |
| The **FIXED** and **IGNORED** chips | Show or hide fixed and ignored findings (each chip shows how many) |
| The **FIND** box, or `/` | Show only findings whose file, message or check contains the text, as you type (`F401`, `Lab05`, `lanecc`...); Enter goes back to the list keeping the search, Escape clears it |
| `f`, the **FIX** button, or a row's **[F] FIX** marker | Apply the suggested fix to the file, then check again (fixable rows end in the marker; long messages end in "…" and show in full in the detail) |
| Highlight a branch (a check, folder or file) | Show a summary of its findings (how many of each severity, by check, and how many can be fixed), the **FIX ALL** button, and every finding in it under its file, with its line, message and suggested fix, to review before fixing them all |
| `f`, **FIX ALL**, or a branch's **[F] FIX N** marker (shown from 2 fixes up) | Fix every fixable finding showing in that branch, after a confirmation, then check again once. A fix that fails (its line changed since the check) is skipped and listed in the branch's summary; the rest still apply |
| `e`, or **View in editor** | For a fixed finding: open the fixed line in VS Code |
| `w`, or **View on site** | For a fixed finding: open the section the fixed link leads to, on the published site |
| `u`, or **Undo** | Put the original text back, then check again |
| `c`, or **Clear** | Forget a fixed finding (the file keeps the fix) |
| `C` | Forget every fixed finding of this course |
| `i`, or **Ignore** / **Un-ignore** | Ignore a finding (with an optional reason), or bring back an ignored one |
| `a`, or **Add to dictionary** | For a spelling finding: add the word to the course's `cspell.json`, so it is never reported again |
| `h` | Show or hide ignored findings (the IGNORED chip) |
| `r` | Run the checks again, after fixing something |
| `ctrl+r` | Hard refresh: run the checks again, asking every web site afresh instead of reusing the day's answers |
| `x`, or **STOP** | Stop a slow check while it runs (its progress shows at the bottom of the list); findings from the checks that finished stay, and `r` checks again |
| `s` | Choose another course folder |
| `q` | Quit |

### Fixing

When a check knows the fix, the finding's panel shows it as a before and after, with a **FIX** button. Fixing edits that one line and nothing else, then checks again. Fixed findings stay in the list, marked FIXED, with the change and whether the re-check still reports the problem, so you can confirm each fix with **View in editor** or **View on site** and undo it if it is wrong. Birdwatcher remembers fixed findings per course folder, in `fixes.json` next to its settings, until you clear them. Birdwatcher never commits; `git diff` shows every change it made.

### Ignoring

Any finding can be ignored, with an optional reason ("kept for last term's students"); ignoring an error asks for confirmation first, because readers are affected. Ignored findings leave the list, and the subtitle counts them; `h` shows them again, with their reasons, and `i` brings one back. Ignores are remembered per course folder in `ignored.json` next to the settings. An ignore matches a finding by its check, file and message rather than its line, so it still applies after lines are added or removed above it.

Files open in the editor chosen on the setup page:

- **VS Code** opens at the exact line. It needs its `code` command on the PATH: the Windows installer adds it; on a Mac, run VS Code's command **Shell Command: Install 'code' command in PATH** once.
- **Typora** opens the file at the top, and Birdwatcher says which line to look at. It is found wherever its installer or the Microsoft Store put it (and in `/Applications` on a Mac).
- **The file's default app** opens it with whatever your system uses for that file type.

## How it works

### The course folder

Birdwatcher reads the course from a local clone, so it sees edits before they are committed: fix a problem, press `r`, and the finding is gone. The chosen folder is saved in `config.json` in your user config folder (on Windows, under `%LOCALAPPDATA%\birdwatcher`).

Pages sometimes link to their own sections with the published site's full address (`https://lcc-cit.github.io/...`). Birdwatcher works out that address from the clone's `origin` remote on GitHub, reading the git config directly, so git itself is not needed. Submodule checkouts work too.

### Findings

Checks produce findings as plain data: the check, the severity, the file and line, and a message. The app and `birdwatcher check` are two views of the same findings, built with [Textual](https://textual.textualize.io/) and [Rich](https://rich.readthedocs.io/). In `birdwatcher check --verbose`, each file and line number is a `vscode://` link that opens it in VS Code.

## Checks

- [x] **Broken section links:** links to a `#section` that doesn't exist on the target page. Section ids follow the site generator's rules, which turn "Architect & Planner" into `architect--planner`; tables of contents generated by other tools often expect `architect-planner`. Fixable when a section with a close id exists.
- [x] **Renumbering leftovers:** files named for a different lab or group than the folder they are in (warnings), and lab folders that share a number (info). Opening a folder finding shows it in your file browser.
- [x] **Stray language labels:** a line reading only "Python" (or "Bash", "PowerShell"...) directly above a code block, left over from pasting code out of an editor or a chat assistant. Fixable: the label moves onto the code block's opening fence (```` ``` ```` becomes ```` ```python ````), so the block gets syntax highlighting; when the fence already names a language, the label is just removed.
- [x] **Skipped heading levels:** a heading more than one level below the previous one, which breaks navigation for screen-reader users. Markdown headings are fixable (moved up to one level below the previous heading).
- [x] **Images without alt text:** images that screen readers cannot describe. An HTML `alt=""` (a decorative image) is fine.
- [x] **Incomplete front matter:** published pages missing a `title`, `description` or `author` (README files are skipped; the site doesn't publish them). Only for a site set up for Jekyll pages (with a `_config.yml`).
- [x] **Dead links:** links and images, in Markdown and HTML pages, that lead to nothing on the published site: missing pages and files (with a "did you mean" when a file has a close name), paths outside the published site, and paths whose letter case only works on Windows and macOS, because the site's server tells `Images/` and `images/` apart (fixable: the path is spelled as the file is).
- [x] **Spelling:** words in the pages (prose and code) and the course's code files (`.py`, `.js`, `.css`) that are not in the dictionary, leaving out minified code (`.min.js`, or any line over 1,000 characters) and whatever the course's `cspell.json` lists in `ignorePaths` (such as a library the course ships), with identifiers split into their words as VS Code's Code Spell Checker does (`maxLength` and `max_length` are checked as "max" and "length"); links, HTML, file names and words with letters outside English are left out. A word with one obvious correction (a known typo, or the only word one letter away) is a warning, fixable in prose (never in code, where it could rename an identifier); a word with none or several is an error; a British spelling is info, fixable to the American one. Code and software words (Python, JavaScript, HTML, CSS, data science, companies' names) are built in, from the MIT-licensed dictionaries Code Spell Checker itself uses, plus a short list of Birdwatcher's own (see `birdwatcher/checks/words/`). A course's own words (people's names, its terms and variable names) live in its `cspell.json`, the file Code Spell Checker reads too; `a` adds a word to it.
- [x] **Dead links to other sites:** asked about over the network, in the background with progress at the bottom of the list (`x` stops it). Errors: pages that are gone (404, 410), server errors (5xx), and addresses nothing answers. Info: sites that turn automated checks away (401, 403, 429, other 4xx; open them in a browser to be sure), and pages that moved permanently to a different address (fixable: the link gets the new address; moves that only add `https`, `www.` or a trailing `/` are skipped). Addresses in the course's `.lycheeignore` or `lychee.toml` `exclude` list are skipped, as are `localhost` addresses. Birdwatcher asks each server about at most two pages at a time, identifies itself as a link checker, and keeps answers for a day in `links.json` next to its settings (server errors and failures are asked again on the next run).
- [x] **Python style:** [Ruff](https://docs.astral.sh/ruff/) over the `.py` files and Jupyter notebooks in the published site, with the course's own rules (`GradingAssistant/ruff.toml`, the ones the labs are graded on; otherwise a `ruff.toml` at the repository root, or whatever settings Ruff finds near the files). Unused imports, undefined names and syntax errors are warnings; the rest is style (info). Notebook findings name the cell. Fixable when Ruff's own fix is safe and changes one line of a `.py` file (on the course today: stray whitespace). Ruff comes with Birdwatcher, and leaves no cache in the course folder.

### Ideas for later

- Python code blocks that don't parse, ignoring `>>>` prompts and deliberate placeholders such as `???`.
- Lab self-numbering: page titles and main headings that name a different lab than their folder.
- Lab completeness: every lab has its instructions, code review form and rubric, and none of them only as a draft.
- License notices on pages that agree with each other and with the repository's `LICENSE` file.
- Analysis of the materials by a large language model (Lab 7).
- Simulated students who attempt a lab using only the published materials (term project).

## Development

| Command | Does |
|---|---|
| `uv run pytest` | Runs the tests. Tests sit next to their module, named `*_test.py`. |
| `uv run ruff check` | Lints with the course style rules (configured in `pyproject.toml`). |
| `uv run ruff format` | Formats the code. |
| `uv run python tools/update_word_lists.py` | Refreshes the built-in spelling word lists from Code Spell Checker's dictionaries on npm. |
| `uv run python -m birdwatcher` | Runs Birdwatcher from the source, the same as `uv run birdwatcher`. |
| `$env:TEXTUAL_DEBUG = "1"; uv run birdwatcher` | Runs the app in Textual's debug mode, which reloads `birdwatcher.tcss` whenever it is saved (PowerShell; in bash, `TEXTUAL_DEBUG=1 uv run birdwatcher`). Debug mode also logs every key and mouse event to `keys.log` in the current folder; it is git-ignored. |

### Project layout

| Folder | Holds |
|---|---|
| `birdwatcher/core/` | Findings, the check interface, running checks over a course folder, and the saved settings. No user interface code. |
| `birdwatcher/checks/` | One module per check, and the registry of all checks. |
| `birdwatcher/ui/` | Console output for `birdwatcher check`, desktop integrations (VS Code, the folder picker), and the Textual app in `ui/tui/`, one module per screen, styled by `birdwatcher.tcss`. |

Dependencies point inward, from `ui` to `checks` to `core`, and a test enforces it. [AGENTS.md](AGENTS.md) has the full working rules: the layers, test-first development, and where new checks, screens and settings go.

## Course materials

The course materials belong to Brian Bird and carry their own license notices. Birdwatcher reads them, and changes a file only when you fix a finding.
