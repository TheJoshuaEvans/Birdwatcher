"""
Contract tests for birdwatcher.checks.spelling (with the real dictionaries).

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import json
import sys

import pytest

from birdwatcher.checks.spelling import CHECK, check_spelling, word_of, words_in
from birdwatcher.core.findings import Finding, Severity


def texts(line):
    return [word.text for word in words_in(line)]


def test_words_are_split_like_cspell():
    words = words_in("Set maxLength of my_list in HTTPServer")
    assert [(w.text, w.standalone) for w in words] == [
        ("Length", False),
        ("list", False),
        ("Server", False),
    ]
    # "Set maxLength of my_list in HTTPServer": Length at 7, list at 20, Server at 32
    assert [w.column for w in words] == [7, 20, 32]


def test_standalone_words_are_marked():
    assert [(w.text, w.standalone) for w in words_in("Hello world")] == [
        ("Hello", True),
        ("world", True),
    ]


@pytest.mark.parametrize(
    "line",
    [
        "see https://example.com/qwertyzz/page",
        "a [link](qwertyzz.md) here",
        '<span class="qwertyzz">',
        "&qwertyzz; entity",
        "mail qwertyzz@example.com",
        "open qwertyzz.py now",
        "in docs/qwertyzz/thing",
        "words with digits qwertyzz2",
        "acronym QWERTYZZ",
        "tiny abc",
    ],
    ids=[
        "url",
        "link-target",
        "html",
        "entity",
        "email",
        "file-name",
        "path",
        "digits",
        "caps",
        "short",
    ],
)
def test_links_html_names_and_such_are_left_out(line):
    assert "qwertyzz" not in " ".join(texts(line)).lower()


def test_contractions_lose_their_ending():
    assert texts("didn't wouldn't") == ["would"]  # "did" is too short
    assert texts("Python's") == ["Python"]
    curly = "\N{RIGHT SINGLE QUOTATION MARK}"
    assert texts(f"didn{curly}t doesn{curly}t") == ["does"]  # "did" is too short


def test_words_with_letters_outside_english_are_left_out():
    assert texts("Jorge Castañón and Tadas Temčinas, Ivan Vulić") == [
        "Jorge",
        "Tadas",
        "Ivan",
    ]


def write(root, path, text):
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text, encoding="utf-8")


def only(root):
    [finding] = check_spelling(root)
    return finding


def test_known_words_are_fine(tmp_path):
    write(tmp_path, "docs/Page.md", "The quick brown fox jumps over the lazy dog.\n")
    assert check_spelling(tmp_path) == []


def test_one_suggestion_is_a_warning_with_a_fix(tmp_path):
    write(tmp_path, "docs/Page.md", "Hello\nLoad the datset first.\n")
    finding = only(tmp_path)
    assert (finding.check, finding.severity, finding.path, finding.line) == (
        CHECK,
        Severity.WARNING,
        "docs/Page.md",
        2,
    )
    assert finding.message.startswith("'datset'")
    assert "dataset" in finding.message
    assert (finding.fix.line, finding.fix.before, finding.fix.after) == (
        2,
        "datset",
        "dataset",
    )


def test_a_fix_keeps_the_word_s_capital(tmp_path):
    write(tmp_path, "docs/Page.md", "Datset loading.\n")
    assert only(tmp_path).fix.after == "Dataset"


def test_several_suggestions_are_an_error_without_a_fix(tmp_path):
    write(tmp_path, "docs/Page.md", "Keep it runing.\n")
    finding = only(tmp_path)
    assert finding.severity == Severity.ERROR
    assert "running" in finding.message and "ruining" in finding.message
    assert finding.fix is None


def test_no_suggestion_is_an_error(tmp_path):
    write(tmp_path, "docs/Page.md", "A zqxjvbwkpf here.\n")
    finding = only(tmp_path)
    assert finding.severity == Severity.ERROR
    assert finding.fix is None


def test_a_british_spelling_is_info_with_the_american_one(tmp_path):
    write(tmp_path, "docs/Page.md", "Pick a colour.\n")
    finding = only(tmp_path)
    assert finding.severity == Severity.INFO
    assert "color" in finding.message
    assert (finding.fix.before, finding.fix.after) == ("colour", "color")


@pytest.mark.parametrize(
    ("path", "text"),
    [
        ("docs/lab.py", "if isinstance(values, numpy.ndarray):\n"),
        ("docs/app.js", "button.onclick = () => localStorage.clear();\n"),
        ("docs/site.css", ".box { flexbox: none; }\n"),
        ("docs/Page.md", "Install Jupyter and scikit-learn with pip.\n"),
    ],
    ids=["python", "javascript", "css", "software-terms"],
)
def test_code_and_software_words_are_built_in(tmp_path, path, text):
    write(tmp_path, path, text)
    assert check_spelling(tmp_path) == []


def test_the_course_word_list_is_respected(tmp_path):
    (tmp_path / "cspell.json").write_text(
        json.dumps({"words": ["Datset", "colour"]}), encoding="utf-8"
    )
    write(tmp_path, "docs/Page.md", "The datset has a colour.\n")
    assert check_spelling(tmp_path) == []


@pytest.mark.parametrize(
    ("path", "text"),
    [
        ("docs/Page.md", "Hello\n```python\nmy_datset = load()\n```\n"),
        ("docs/Page.md", "Use `datset` here.\n"),
        ("docs/lab.py", "datset = load()\n"),
    ],
    ids=["code-block", "inline-code", "python-file"],
)
def test_code_is_checked_but_never_fixed(tmp_path, path, text):
    write(tmp_path, path, text)
    finding = only(tmp_path)
    assert finding.message.startswith("'datset'")
    assert finding.path == path
    assert finding.fix is None


@pytest.mark.parametrize(
    ("path", "text"),
    [("docs/app.js", "let datset = load();\n"), ("docs/site.css", ".datset { }\n")],
    ids=["javascript", "css"],
)
def test_javascript_and_css_are_checked_as_code(tmp_path, path, text):
    write(tmp_path, path, text)
    finding = only(tmp_path)
    assert (finding.path, finding.fix) == (path, None)
    assert finding.message.startswith("'datset'")


@pytest.mark.parametrize("name", ["jquery.min.js", "bootstrap.min.css"])
def test_minified_files_are_left_out(tmp_path, name):
    write(tmp_path, f"docs/{name}", "datset\n")
    assert check_spelling(tmp_path) == []


def test_a_code_file_with_a_very_long_line_counts_as_minified(tmp_path):
    write(tmp_path, "docs/tex-chtml.js", "datset\n" + "var a=1;" * 200 + "\n")
    assert check_spelling(tmp_path) == []


def test_a_saved_web_page_s_files_are_left_out(tmp_path):
    write(tmp_path, "docs/Notes/Article_files/player.js", "let datset = 1;\n")
    write(tmp_path, "docs/Notes/Article_files/theme.css", ".datset {}\n")
    write(tmp_path, "docs/Labs/Rubric.fld/stylesheet.css", ".datset {}\n")  # Office's
    assert check_spelling(tmp_path) == []


def test_the_course_s_cspell_ignore_paths_are_followed(tmp_path):
    (tmp_path / "cspell.json").write_text(
        json.dumps({"ignorePaths": ["**/ace-builds/**", "Drafts"]}), encoding="utf-8"
    )
    write(tmp_path, "docs/Lessons/ace-builds/src/mode-php.js", "datset\n")
    write(tmp_path, "docs/Drafts/Old.md", "datset\n")
    write(tmp_path, "docs/Lessons/Page.md", "datset\n")
    assert [f.path for f in check_spelling(tmp_path)] == ["docs/Lessons/Page.md"]


def test_no_fix_when_the_text_comes_earlier_in_the_line(tmp_path):
    write(tmp_path, "docs/Page.md", "Mydatsets and datset.\n")
    findings = [f for f in check_spelling(tmp_path) if f.message.startswith("'datset'")]
    assert [f.fix for f in findings] == [None]


def test_word_of_reads_back_the_word():
    write_finding = Finding(CHECK, Severity.ERROR, "docs/P.md", 1, "'Hte' is not ...")
    assert word_of(write_finding) == "Hte"
    other = Finding("links", Severity.ERROR, "docs/P.md", 1, "'Hte' is not ...")
    assert word_of(other) is None


def test_findings_are_in_file_and_line_order(tmp_path):
    write(tmp_path, "docs/B.md", "datset\n\nzqxjvbwkpf\n")
    write(tmp_path, "docs/A.md", "zqxjvbwkpf\n")
    assert [(f.path, f.line) for f in check_spelling(tmp_path)] == [
        ("docs/A.md", 1),
        ("docs/B.md", 1),
        ("docs/B.md", 3),
    ]


def test_no_docs_folder_means_no_findings(tmp_path):
    assert check_spelling(tmp_path) == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
