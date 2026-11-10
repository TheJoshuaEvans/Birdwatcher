"""
Integrations with the user's desktop: VS Code, the file browser and the
system's folder picker.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import os
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

EDITOR_COMMAND = "code"  # VS Code's command-line launcher
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


def show_in_file_browser(folder):
    """
    Show a folder in the system's file browser (Explorer on Windows, Finder on
    a Mac, the desktop's default elsewhere), without waiting for it.

    Args:
        folder (Path): The folder.

    Raises:
        OSError: The file browser could not be started.
    """
    if sys.platform == "win32":
        os.startfile(folder)
    else:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen(
            [opener, str(folder)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


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
