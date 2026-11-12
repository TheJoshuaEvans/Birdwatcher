"""
Stray language labels: a lone "Python" (or another language's name) on its own
line just above a code block.

Copying code out of an editor or a chat often brings the editor's language
label along; on the published page it shows as a stray word above the code.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import re
from pathlib import Path

from birdwatcher.checks.pages import FENCE, TEXT, line_kinds, read_page, site_pages
from birdwatcher.core.course import site_folder
from birdwatcher.core.findings import Edit, Finding, Fix, Severity

CHECK = "stray-language-label"
# An opening fence: its marker (``` or ~~~, or longer) and its info string
FENCE_MARKER = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
# Labels whose fence language (as Jekyll's highlighter, Rouge, names it) is not
# simply the label in lower case
FENCE_TAGS = {"c#": "csharp", "c++": "cpp", "terminal": "console", "output": "text"}
LANGUAGE_NAMES = frozenset(
    {
        "python",
        "py",
        "bash",
        "shell",
        "sh",
        "powershell",
        "console",
        "terminal",
        "javascript",
        "js",
        "typescript",
        "ts",
        "json",
        "c#",
        "csharp",
        "c++",
        "cpp",
        "html",
        "css",
        "sql",
        "yaml",
        "text",
        "plaintext",
        "output",
    }
)


def check_labels(repo_root):
    """
    Find prose lines that hold nothing but a programming language's name, when
    the next non-blank line opens a code block.

    Looks at every site page under docs/ (see pages.site_pages). The name is
    matched without regard to case and surrounding spaces; recognized names
    include Python, Bash, PowerShell, JavaScript, JSON, C#, C++, HTML, CSS, SQL,
    YAML, Text and Output. Lines in front matter or code are never reported.

    Args:
        repo_root (Path): Root folder of the course repository.

    Returns:
        list[Finding]: A warning per stray label, at its line, in path and
            line order, each with a Fix that removes the label (the line is
            left empty). When the code block's opening fence names no
            language, the fix also adds the label's language to it (in
            lower case, or as FENCE_TAGS says), so the block is highlighted.
            Empty when the course has no pages.
    """
    repo_root = Path(repo_root).resolve()
    docs = site_folder(repo_root)
    if not docs.is_dir():
        return []
    findings = []
    for page in site_pages(docs):
        lines = line_kinds(read_page(page))
        for index, (kind, line) in enumerate(lines):
            label = line.strip()
            if kind != TEXT or label.lower() not in LANGUAGE_NAMES:
                continue
            fence_index = next(
                (i for i in range(index + 1, len(lines)) if lines[i][1].strip()), None
            )
            # Prose is followed by a fence only where a code block opens.
            if fence_index is None or lines[fence_index][0] != FENCE:
                continue
            message = (
                f'A stray "{label}" line sits just above a code block, so it '
                "shows on the page as a lone word. It is usually left over "
                "from copying code out of an editor."
            )
            also = ()
            opening = FENCE_MARKER.match(lines[fence_index][1])
            if opening and not opening.group(2).strip():
                # A bare fence: the label becomes the block's language.
                marker = opening.group(1)
                tag = FENCE_TAGS.get(label.lower(), label.lower())
                also = (Edit(fence_index + 1, marker, marker + tag),)
                message += (
                    f" Moving it onto the block's opening fence ({marker}{tag}) "
                    "also gives the block syntax highlighting."
                )
            findings.append(
                Finding(
                    check=CHECK,
                    severity=Severity.WARNING,
                    path=page.relative_to(repo_root).as_posix(),
                    line=index + 1,
                    message=message,
                    fix=Fix(line=index + 1, before=label, after="", also=also),
                )
            )
    return findings
