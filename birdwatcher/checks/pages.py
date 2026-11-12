"""
Reading the course site's Markdown pages: which pages there are, and which of
their lines are front matter, code fences, code, or prose.

Shared by the checks that read pages.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import re

FRONT_MATTER = re.compile(r"\A---[ \t]*\n(.*?)\n?---[ \t]*(?:\n|\Z)", re.DOTALL)
# Any indentation: a fence nested in a list item sits deeper than three spaces.
FENCE_OPEN = re.compile(r"^[ \t]*(`{3,}|~{3,})")
FRONT_KEY = re.compile(r"^([A-Za-z_][\w-]*)[ \t]*:[ \t]*(.*?)[ \t]*$")

FRONT, FENCE, CODE, TEXT = "front matter", "fence", "code", "text"  # line kinds

# Links. A target is either <anything but angle brackets> or has no spaces.
_TARGET = r"\(\s*(?:<(?P<angled>[^<>\n]+)>|(?P<bare>[^\s<>()]+))(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)"
INLINE_LINK = re.compile(r"(?<!!)\[(?:[^\[\]]|\[[^\[\]]*\])*\]" + _TARGET)
INLINE_IMAGE = re.compile(r"!\[[^\[\]]*\]" + _TARGET)
REFERENCE_DEFINITION = re.compile(
    r"^ {0,3}\[(?!\^)[^\]]+\]:[ \t]*(?:<(?P<angled>[^<>\n]+)>|(?P<bare>\S+))"
)
HTML_ATTRIBUTE = re.compile(
    r"""\b(?:href|src)\s*=\s*["'](?P<bare>[^"']+)["']""", re.IGNORECASE
)
INLINE_CODE = re.compile(r"(`+)(.+?)\1")
# Blocks of an HTML page that hold no links: styles, scripts, and code examples
STYLE_OR_SCRIPT = re.compile(
    r"<(style|script|pre|code)\b.*?</\1\s*>", re.IGNORECASE | re.DOTALL
)


def site_pages(docs, suffixes=(".md",)):
    """
    The site's pages: every file under docs/ with one of the suffixes (by
    default its Markdown pages), except in folders whose names start with "_"
    (Jekyll's own) or "." (hidden).

    Args:
        docs (Path): The docs/ folder.
        suffixes (Sequence[str]): The kinds of page wanted, lowercase with
            the dot, e.g. (".md", ".html").

    Returns:
        list[Path]: In path order.
    """
    pages = (
        page
        for page in docs.rglob("*")
        if page.suffix.lower() in suffixes
        and page.is_file()
        and not any(
            part.startswith(("_", ".")) for part in page.relative_to(docs).parts[:-1]
        )
    )
    return sorted(pages, key=lambda page: page.relative_to(docs).as_posix())


def read_page(page):
    """
    A page's text, with Windows line endings turned into "\\n".

    Args:
        page (Path): The page.

    Returns:
        str: The text; undecodable bytes are replaced rather than raising.
    """
    return page.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")


def line_kinds(text):
    """
    What each line of a page is.

    Args:
        text (str): The page's text, as from read_page.

    Returns:
        list[tuple[str, str]]: (kind, line) for every line, in order. The kind
            is FRONT for the front matter block at the very top (both "---"
            lines included), FENCE for a line opening or closing a ``` or ~~~
            code block, CODE inside such a block (to the end of the page if it
            is never closed), and TEXT otherwise.
    """
    lines = text.split("\n")
    kinds = [TEXT] * len(lines)
    front = FRONT_MATTER.match(text)
    first = 0
    if front:
        first = front.group(0).rstrip("\n").count("\n") + 1
        kinds[:first] = [FRONT] * first
    fence = None
    for index in range(first, len(lines)):
        line = lines[index]
        if fence is not None:
            closing = re.match(
                rf"^[ \t]*{re.escape(fence[0])}{{{len(fence)},}}[ \t]*$", line
            )
            kinds[index] = FENCE if closing else CODE
            if closing:
                fence = None
            continue
        opening = FENCE_OPEN.match(line)
        if opening:
            fence = opening.group(1)
            kinds[index] = FENCE
    return list(zip(kinds, lines, strict=True))


def prose_lines(text):
    """
    A page's lines with everything but prose blanked out, so line numbers stay
    true while front matter and code are ignored.

    Args:
        text (str): The page's text.

    Returns:
        list[str]: One entry per line: the line itself for TEXT lines, "" for
            the others.
    """
    return [line if kind == TEXT else "" for kind, line in line_kinds(text)]


def page_links(text, html=False):
    """
    Every link and image target in a page's prose.

    Finds Markdown links and images ("[text](target)", "![alt](target)", with
    an optional title), link reference definitions ("[name]: target"), and
    HTML href and src attributes. Front matter, fenced code blocks, inline
    code and footnotes ("[^1]: text") are left out.

    Args:
        text (str): The page's text, as from read_page.
        html (bool): True for an HTML page: only href and src attributes
            count, outside <style>, <script>, <pre> and <code> blocks (code
            examples show links, they are not links), and Markdown syntax
            means nothing.

    Returns:
        list[tuple[int, str]]: (line number, target) in page order, the
            target exactly as written (angle brackets around it removed).
    """
    if html:
        # Blank the blocks out character by character so line numbers stay true.
        text = STYLE_OR_SCRIPT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
        return [
            (number, match.group("bare"))
            for number, line in enumerate(text.split("\n"), start=1)
            for match in HTML_ATTRIBUTE.finditer(line)
        ]
    found = []
    for number, line in enumerate(prose_lines(text), start=1):
        line = INLINE_CODE.sub(lambda match: " " * len(match.group(0)), line)
        targets = []
        for pattern in (
            INLINE_LINK,
            INLINE_IMAGE,
            REFERENCE_DEFINITION,
            HTML_ATTRIBUTE,
        ):
            for match in pattern.finditer(line):
                group = "angled" if match.groupdict().get("angled") else "bare"
                targets.append((match.start(group), match.group(group)))
        found.extend((number, target) for _, target in sorted(targets))
    return found


def front_matter(text):
    """
    The top-level keys of a page's front matter.

    Only simple "key: value" lines at the start of a line count; nested and
    list entries are ignored.

    Args:
        text (str): The page's text.

    Returns:
        dict[str, str] | None: Each key and its value as written (quotes
            kept), or None when the page has no front matter block.
    """
    match = FRONT_MATTER.match(text)
    if match is None:
        return None
    found = {}
    for line in match.group(1).split("\n"):
        key = FRONT_KEY.match(line)
        if key:
            found[key.group(1)] = key.group(2)
    return found
