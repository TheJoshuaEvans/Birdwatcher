# Birdwatcher

Watches the course materials of CS 212, AI Programming 1 at Lane Community College, for consistency problems and blind spots.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)

## What it does

Birdwatcher runs static checks over a local clone of Brian Bird's course repository, [lcc-cit/CS212-CourseMaterials](https://github.com/lcc-cit/CS212-CourseMaterials), and shows each problem it finds in an interactive terminal app: open the exact file and line in an editor, fix it, and re-run the checks to confirm the fix.

The course repository already checks that its links resolve, using [lychee](https://lychee.cli.rs/) in GitHub Actions. Birdwatcher looks for what a link checker can't see: links to sections that don't exist, files left over from renumbering, accessibility problems, and code that breaks the course's own style rules.

**Status:** early development, as the CS 212 Lab 6 project. It grows into the term project: Lab 7 adds analysis by a large language model, and the term project adds simulated students. Downloading, caching, the app and the first check work; the other checks below are being built.

## Setup

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

The first time the app opens, it asks for the folder of your local clone of the course repository (the folder that contains `docs/`) and remembers it. Type or paste the path, or press **Browse…** (Ctrl+O) to pick it in your system's folder picker. The setup page (`s`) also lists your recent course folders, so switching between courses is one click, and lets you choose the editor that opens files. `birdwatcher check` uses the same folder unless `--course-dir` names another.

In the app, mouse and keyboard both work:

| Do | To |
|---|---|
| Click a finding, or `n` / `p` (next / previous finding) | Show it: check, location, message, and the source lines around it |
| Click it again, or press Enter or `o` | Open the file at that line in your editor |
| Click a branch, or the arrow keys and Enter | Fold or unfold it |
| The **Check / Severity / Folder** tabs, or `g` | Group the findings by check, by severity, or by folder |
| The **FIXED** and **IGNORED** chips | Show or hide fixed and ignored findings (each chip shows how many) |
| `f`, or the **FIX** button | Apply the suggested fix to the file, then check again |
| `e`, or **View in editor** | For a fixed finding: open the fixed line in VS Code |
| `w`, or **View on site** | For a fixed finding: open the section the fixed link leads to, on the published site |
| `u`, or **Undo** | Put the original text back, then check again |
| `c`, or **Clear** | Forget a fixed finding (the file keeps the fix) |
| `C` | Forget every fixed finding of this course |
| `i`, or **Ignore** / **Un-ignore** | Ignore a finding (with an optional reason), or bring back an ignored one |
| `h` | Show or hide ignored findings (the IGNORED chip) |
| `r` | Run the checks again, after fixing something |
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
- [ ] **Stray language labels:** a line reading only "Python" directly above a code block, left over from pasting code in an editor.
- [ ] **Skipped heading levels:** a heading more than one level below the previous one, which breaks navigation for screen-reader users.
- [ ] **Images without alt text:** images that screen readers cannot describe.
- [ ] **Incomplete front matter:** pages missing a `title`, `description` or `author`.
- [ ] **Python style:** [Ruff](https://docs.astral.sh/ruff/) over the course's `.py` files, using the rules from the course's own `PythonStyleAndBestPracticesChecklist.md`.

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
| `uv run python -m birdwatcher` | Runs Birdwatcher from the source, the same as `uv run birdwatcher`. |

### Project layout

| Folder | Holds |
|---|---|
| `birdwatcher/core/` | Findings, the check interface, running checks over a course folder, and the saved settings. No user interface code. |
| `birdwatcher/checks/` | One module per check, and the registry of all checks. |
| `birdwatcher/ui/` | Console output for `birdwatcher check`, desktop integrations (VS Code, the folder picker), and the Textual app in `ui/tui/`, one module per screen, styled by `birdwatcher.tcss`. |

Dependencies point inward, from `ui` to `checks` to `core`, and a test enforces it. [AGENTS.md](AGENTS.md) has the full working rules: the layers, test-first development, and where new checks, screens and settings go.

## Course materials

The course materials belong to Brian Bird and carry their own license notices. Birdwatcher reads them, and changes a file only when you fix a finding.
