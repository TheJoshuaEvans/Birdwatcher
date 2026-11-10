"""
Integrations with the user's desktop: editors (VS Code, Typora, the default
app), the file browser and the system's folder picker.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import os
import shutil
import subprocess
import sys
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

EDITOR_COMMAND = "code"  # VS Code's command-line launcher
VSCODE, TYPORA, DEFAULT_APP = "vscode", "typora", "default"  # editor ids
FOLDER_PICKER_TITLE = "Choose the course repository's folder"


def editor_url(path, line=None):
    """
    A link that opens a file in VS Code, at a line when one is given.

    Args:
        path (PurePath): The file's absolute path, Windows or POSIX style.
        line (int | None): The 1-based line, or None for the whole file.

    Returns:
        str: "vscode://file/<path with forward slashes>[:<line>]", with spaces,
            "#" and other unsafe characters percent-encoded.
    """
    # VS Code wants exactly one slash after "file", for drive letters and
    # POSIX roots alike.
    location = urllib.parse.quote(path.as_posix().lstrip("/"), safe="/:")
    url = f"vscode://file/{location}"
    return url if line is None else f"{url}:{line}"


def open_in_vscode(path, line):
    """
    Open a file in VS Code with the cursor on a line, without waiting for it.

    Args:
        path (Path): The file.
        line (int): The 1-based line number.

    Raises:
        FileNotFoundError: VS Code's `code` command is not on the PATH. (On a
            Mac, VS Code's command "Shell Command: Install 'code' command in
            PATH" adds it.)
    """
    command = shutil.which(EDITOR_COMMAND)
    if command is None:
        raise FileNotFoundError(
            f"VS Code's '{EDITOR_COMMAND}' command is not on the PATH"
        )
    subprocess.Popen(
        [command, "--goto", f"{path}:{line}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


@dataclass(frozen=True)
class Editor:
    """
    An editor Birdwatcher can open course files in.

    Attributes:
        id (str): The id saved in the settings, e.g. "vscode".
        name (str): Its name for people, e.g. "VS Code".
        opens_at_line (bool): Whether it puts the cursor on the given line;
            when False, the file opens at the top.
        available (bool): Whether it was found on this computer.
        open (Callable[[Path, int], object]): Opens a file at a 1-based line
            (or at the top, see opens_at_line), without waiting. Raises
            OSError when the editor cannot be started.
    """

    id: str
    name: str
    opens_at_line: bool
    available: bool
    open: Callable[[Path, int], object]


def desktop_editors():
    """
    The editors Birdwatcher offers, looked up on this computer.

    Returns:
        dict[str, Editor]: "vscode" (VS Code, at the line, when its `code`
            command is on the PATH), "typora" (Typora, at the top of the file,
            when installed) and "default" (the system's default app for the
            file type, at the top, always available), in that order.
    """
    typora = find_typora()
    return {
        VSCODE: Editor(
            VSCODE,
            "VS Code",
            True,
            shutil.which(EDITOR_COMMAND) is not None,
            open_in_vscode,
        ),
        TYPORA: Editor(
            TYPORA,
            "Typora",
            False,
            typora is not None,
            lambda path, line: _launch([*(typora or ["typora"]), str(path)]),
        ),
        DEFAULT_APP: Editor(
            DEFAULT_APP,
            "The file's default app",
            False,
            True,
            lambda path, line: _open_with_system(path),
        ),
    }


def find_typora():
    """
    Find Typora on this computer.

    Looks where installers put it: on Windows, the App Paths registry entry
    (per user, then per machine, as the Microsoft Store and the installer
    register it) and the usual install folders; on a Mac, Typora.app in
    /Applications or ~/Applications; elsewhere, `typora` on the PATH.

    Returns:
        list[str] | None: The command that opens a file in Typora (the file's
            path goes after it), or None when Typora was not found.
    """
    if sys.platform == "win32":
        found = _typora_from_registry() or next(
            (str(path) for path in _windows_typora_folders() if path.is_file()), None
        )
        return [found] if found else None
    if sys.platform == "darwin":
        apps = [Path("/Applications"), Path.home() / "Applications"]
        if any((folder / "Typora.app").is_dir() for folder in apps):
            return ["open", "-a", "Typora"]
        return None
    found = shutil.which("typora")
    return [found] if found else None


def _typora_from_registry():
    import winreg  # Windows only, so imported here

    key = r"Software\Microsoft\Windows\CurrentVersion\App Paths\Typora.exe"
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, key) as entry:
                path = winreg.QueryValue(entry, None)
        except OSError:
            continue
        if path and Path(path).is_file():
            return path
    return None


def _windows_typora_folders():
    for variable in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(variable)
        if base:
            folder = "Programs/Typora" if variable == "LOCALAPPDATA" else "Typora"
            yield Path(base) / folder / "Typora.exe"


def _launch(command):
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _open_with_system(path):
    if sys.platform == "win32":
        os.startfile(path)
    else:
        _launch(["open" if sys.platform == "darwin" else "xdg-open", str(path)])


def show_in_file_browser(folder):
    """
    Show a folder in the system's file browser (Explorer on Windows, Finder on
    a Mac, the desktop's default elsewhere), without waiting for it.

    Args:
        folder (Path): The folder.

    Raises:
        OSError: The file browser could not be started.
    """
    _open_with_system(folder)


def choose_folder_dialog(start):
    """
    Ask for a folder with the system's own folder picker (Explorer's on
    Windows, Finder's on a Mac), shown in front of other windows. Blocks until
    it closes, so call it on the main thread (macOS requires that).

    Args:
        start (Path | None): The folder to start in; None or a missing folder
            starts in the picker's default place.

    Returns:
        Path | None: The chosen folder, or None when the picker was cancelled.

    Raises:
        OSError: No folder picker can be shown (for example, Python without
            Tk, or no desktop session).
    """
    # Imported here so the app still runs on a Python built without Tk.
    try:
        import tkinter
        from tkinter import filedialog
    except ImportError as error:
        raise OSError(f"Python has no Tk: {error}") from error
    try:
        root = tkinter.Tk()
    except tkinter.TclError as error:
        raise OSError(str(error)) from error
    try:
        # A hidden, topmost parent brings the picker in front of the terminal.
        root.withdraw()
        root.attributes("-topmost", True)
        options = {"title": FOLDER_PICKER_TITLE, "mustexist": True}
        if start is not None and Path(start).is_dir():
            options["initialdir"] = str(start)
        chosen = filedialog.askdirectory(parent=root, **options)
    finally:
        root.destroy()
    # Cancelling returns "" (or an empty tuple on some platforms).
    return Path(chosen) if chosen else None
