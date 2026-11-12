"""
Stray language labels: a lone "Python" (or another language's name) on its own
line just above a code block.

Copying code out of an editor or a chat often brings the editor's language
label along; on the published page it shows as a stray word above the code.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from pathlib import Path

from birdwatcher.checks.pages import FENCE, TEXT, line_kinds, read_page, site_pages
from birdwatcher.core.course import site_folder
from birdwatcher.core.findings import Finding, Fix, Severity

CHECK = "stray-language-label"
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
            left empty). Empty when the repository has no docs/ folder.
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
            following = next(
                (k for k, text in lines[index + 1 :] if text.strip()), None
            )
            # Prose is followed by a fence only where a code block opens.
            if following != FENCE:
                continue
            findings.append(
                Finding(
                    check=CHECK,
                    severity=Severity.WARNING,
                    path=page.relative_to(repo_root).as_posix(),
                    line=index + 1,
                    message=(
                        f'A stray "{label}" line sits just above a code block, so it '
                        "shows on the page as a lone word. It is usually left over "
                        "from copying code out of an editor."
                    ),
                    fix=Fix(line=index + 1, before=label, after=""),
                )
            )
    return findings
