"""
Spelling: words in the course's pages and Python files that are not in the
dictionary, cspell-style (identifiers are split into their words).

Words come from every line of the site's Markdown pages, code included, and
of the .py files under docs/; links, HTML and file names are left out. A
word is fine when it is in the course's own word list (core.dictionary) or
in the English dictionary (pyspellchecker). British spellings are noted with
their American spelling (codespell's list). Suggestions come from codespell's
list of common misspellings first, then from dictionary words one edit away
(an obvious replacement; two edits away would be both far-fetched and slow).

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import re
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from pathlib import Path

from spellchecker import SpellChecker

from birdwatcher.checks.pages import CODE, FENCE, line_kinds, read_page, site_pages
from birdwatcher.core.course import DOCS_FOLDER
from birdwatcher.core.dictionary import course_words
from birdwatcher.core.findings import Finding, Fix, Severity

CHECK = "spelling"
MIN_LENGTH = 4  # shorter words are not checked (cspell's default)
MAX_SUGGESTIONS = 5  # shown in a message

FILE_EXTENSIONS = (
    "md|py|html?|ipynb|txt|csv|json|toml|ya?ml|png|jpe?g|gif|svg|pdf|js|css|zip"
    "|docx|pptx|xlsx|sh|ps1|exe"
)
LEFT_OUT = re.compile(
    r"https?://\S+|www\.\S+"  # addresses
    r"|\]\([^)]*\)"  # Markdown link targets
    r"|<[^>]*>"  # HTML tags
    r"|&#?\w+;"  # HTML entities
    r"|\S+@\S+"  # e-mail addresses
    r"|\S*[/\\]\S*"  # paths
    rf"|[\w.-]+\.(?:{FILE_EXTENSIONS})\b",  # file names
    re.IGNORECASE,
)
# Any letters, so a name such as Castañón stays one token (and is left out);
# ’ is a typographic apostrophe.
TOKEN = re.compile(r"[\w'\N{RIGHT SINGLE QUOTATION MARK}]+")
CONTRACTION = re.compile(r"(?:n't|'s|'re|'ve|'ll|'d|'m)$", re.IGNORECASE)
PART = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+")
INLINE_CODE = re.compile(r"(`+).+?\1")
QUOTED_WORD = re.compile(r"^'([^']+)'")


@dataclass(frozen=True)
class Word:
    """
    A word to check, found in a line.

    Attributes:
        text (str): The word, as written.
        column (int): Where it starts in the line, from 0.
        standalone (bool): True when it is a whole token of its own, not a
            part of an identifier such as max_length or maxLength.
    """

    text: str
    column: int
    standalone: bool


def words_in(line):
    """
    The words of a line worth checking.

    URLs, Markdown link targets, HTML tags and entities, e-mail addresses,
    file names (a name with an extension) and paths (anything with a slash)
    are left out, and so are words with letters outside English (Castañón).
    Tokens are split at "_" and at camelCase humps ("HTTPServer" gives
    "HTTP" and "Server"); a contraction loses its ending ("didn't" or
    "didn’t" gives "did"). Parts in capitals (acronyms), with digits, or
    shorter than MIN_LENGTH are left out.

    Args:
        line (str): One line of a page or file.

    Returns:
        list[Word]: In line order.
    """
    # Blank out what is left out, keeping every other character's column.
    line = LEFT_OUT.sub(lambda match: " " * len(match.group(0)), line)
    words = []
    for token in TOKEN.finditer(line):
        text, start = token.group(0), token.start()
        text = text.replace("\N{RIGHT SINGLE QUOTATION MARK}", "'")
        if not text.isascii():
            continue  # letters outside English
        stripped = text.lstrip("'")
        start += len(text) - len(stripped)
        text = CONTRACTION.sub("", stripped.rstrip("'"))
        if not text or "'" in text or any(c.isdigit() for c in text):
            continue
        parts = list(PART.finditer(text))
        whole = len(parts) == 1 and parts[0].group(0) == text
        for part in parts:
            word = part.group(0)
            if len(word) < MIN_LENGTH or word.isupper():
                continue
            words.append(Word(word, start + part.start(), whole))
    return words


def check_spelling(repo_root):
    """
    Find words not in the dictionary in the site's Markdown pages and the
    .py files under docs/.

    Args:
        repo_root (Path): Root folder of the course repository.

    Returns:
        list[Finding]: One per word, in file and line order. Each message
            starts with the word in quotes ('colour' ...):
            - a British spelling: info, naming the American spelling;
            - not in the dictionary with exactly one suggestion: a warning
              ("Did you mean ...?");
            - not in the dictionary with no suggestion or several: an error
              (naming up to MAX_SUGGESTIONS of them).
            A finding has a Fix to the one suggestion (or American spelling),
            in the word's letter case, only when the word is in prose (not a
            code block, inline code or a .py file), stands alone, and is the
            first occurrence of that text on its line. Empty when the
            repository has no docs/ folder.
    """
    repo_root = Path(repo_root).resolve()
    docs = repo_root / DOCS_FOLDER
    if not docs.is_dir():
        return []
    known = course_words(repo_root)
    verdicts = {}  # lowercased word -> (severity, options) or None

    def verdict(word):
        key = word.lower()
        if key not in verdicts:
            verdicts[key] = _verdict(key, known)
        return verdicts[key]

    findings = []
    for page in site_pages(docs, suffixes=(".md", ".py")):
        path = page.relative_to(repo_root).as_posix()
        for number, line, code_spans in _lines(page):
            for word in words_in(line):
                found = verdict(word.text)
                if found is None:
                    continue
                severity, options = found
                in_code = code_spans is None or any(
                    start <= word.column < end for start, end in code_spans
                )
                fix = None
                if (
                    len(options) == 1
                    and word.standalone
                    and not in_code
                    and line.find(word.text) == word.column
                ):
                    fix = Fix(number, word.text, _same_case(word.text, options[0]))
                message = _message(word.text, severity, options)
                findings.append(Finding(CHECK, severity, path, number, message, fix))
    return sorted(findings, key=lambda finding: (finding.path, finding.line))


def word_of(finding):
    """
    The word a spelling finding is about.

    Args:
        finding (Finding): Any finding.

    Returns:
        str | None: The word, or None for another check's finding.
    """
    if finding.check != CHECK:
        return None
    quoted = QUOTED_WORD.match(finding.message)
    return quoted.group(1) if quoted else None


def _lines(page):
    """Yield (line number, line, code spans) for a page or file. The spans
    are (start, end) columns of inline code; None means the whole line is code."""
    text = read_page(page)
    if page.suffix.lower() == ".py":
        for number, line in enumerate(text.split("\n"), start=1):
            yield number, line, None
        return
    for number, (kind, line) in enumerate(line_kinds(text), start=1):
        if kind == FENCE:
            continue
        if kind == CODE:
            yield number, line, None
        else:
            spans = [(m.start(), m.end()) for m in INLINE_CODE.finditer(line)]
            yield number, line, spans


def _verdict(key, known):
    """(severity, options) for a lowercased word, or None when it is fine."""
    if key in known:
        return None
    british = _british().get(key)
    if british:
        return Severity.INFO, british
    if _english().known([key]):
        return None
    options = _typos().get(key) or _suggestions(key)
    return (Severity.WARNING if len(options) == 1 else Severity.ERROR), options


def _suggestions(key):
    """Dictionary words one edit from an unknown word, most common first."""
    checker = _english()
    options = (checker.candidates(key) or set()) - {key}
    return sorted(options, key=lambda w: (-checker.word_usage_frequency(w), w))


def _message(word, severity, options):
    if severity == Severity.INFO:
        return f"'{word}' is the British spelling; American English writes '{' or '.join(options)}'."
    if len(options) == 1:
        return f"'{word}' is not in the dictionary. Did you mean '{options[0]}'?"
    if options:
        shown = ", ".join(options[:MAX_SUGGESTIONS])
        return f"'{word}' is not in the dictionary. Did you mean one of: {shown}?"
    return f"'{word}' is not in the dictionary, and no word is close to it."


def _same_case(word, replacement):
    """The replacement in the word's letter case (Capitalized or lower)."""
    return (
        replacement[:1].upper() + replacement[1:] if word[:1].isupper() else replacement
    )


@cache
def _english():
    return SpellChecker(distance=1)


@cache
def _typos():
    return _codespell_list("dictionary.txt")


@cache
def _british():
    return _codespell_list("dictionary_en-GB_to_en-US.txt")


def _codespell_list(name):
    """codespell's "wrong->right, other," lines as {wrong: [right, other]}; a
    reason it gives instead of a correction ("disabled because ...") is
    dropped."""
    table = {}
    text = files("codespell_lib").joinpath("data", name).read_text(encoding="utf-8")
    for line in text.splitlines():
        wrong, _, right = line.partition("->")
        options = [o.strip() for o in right.split(",")]
        table[wrong.strip().lower()] = [o for o in options if o and " " not in o]
    return table
