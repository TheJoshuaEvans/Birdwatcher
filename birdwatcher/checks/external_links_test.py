"""
Contract tests for birdwatcher.checks.external_links, with a fake look-up in
place of the network.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import sys

import pytest

from birdwatcher.checks.external_links import (
    CHECK,
    OfflineError,
    check_external_links,
)
from birdwatcher.core.findings import Severity
from birdwatcher.core.web import LinkStatus

SITE = "https://lcc-cit.github.io/CS212-CourseMaterials/"
URL = "https://example.com/page"
OK = LinkStatus(200)


class FakeLookUp:
    """Answers from a dict (unknown addresses answer 200); records what it was
    asked and the progress callback it got."""

    def __init__(self, answers=None):
        self.answers = answers or {}
        self.asked = []
        self.progress = None

    def __call__(self, urls, report_progress):
        self.asked.append(sorted(urls))
        self.progress = report_progress
        return {url: self.answers.get(url, OK) for url in urls}


def make_page(root, text, name="Notes.md"):
    page = root / "docs" / name
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(text, encoding="utf-8")


def check(root, answers=None, site_url=SITE):
    look_up = FakeLookUp(answers)
    return check_external_links(root, site_url, look_up), look_up


@pytest.mark.parametrize(
    ("answer", "severity", "words"),
    [
        (LinkStatus(404), Severity.ERROR, "404"),
        (LinkStatus(410), Severity.ERROR, "410"),
        (LinkStatus(502), Severity.ERROR, "502"),
        (LinkStatus(None, error="timed out"), Severity.ERROR, "timed out"),
        (LinkStatus(403), Severity.INFO, "browser"),
        (LinkStatus(401), Severity.INFO, "browser"),
        (LinkStatus(429), Severity.INFO, "browser"),
        (LinkStatus(400), Severity.INFO, "browser"),
    ],
    ids=["404", "410", "502", "no-answer", "403", "401", "429", "400"],
)
def test_answers_that_are_not_ok_are_reported(tmp_path, answer, severity, words):
    make_page(tmp_path, f"Intro\nSee [it]({URL}).\n")
    [finding], _ = check(tmp_path, {URL: answer})
    assert (finding.check, finding.severity, finding.path, finding.line) == (
        CHECK,
        severity,
        "docs/Notes.md",
        2,
    )
    assert URL in finding.message
    assert words in finding.message
    assert finding.fix is None


@pytest.mark.parametrize("status", [200, 204, 299])
def test_working_addresses_are_fine(tmp_path, status):
    make_page(tmp_path, f"[it]({URL})\n")
    assert check(tmp_path, {URL: LinkStatus(status)})[0] == []


def test_a_permanent_move_is_info_with_a_fix_to_the_new_address(tmp_path):
    moved = "https://www.example.org/new/place"
    make_page(tmp_path, f"Intro\n[it]({URL}#part) and more\n")
    [finding], _ = check(tmp_path, {URL: LinkStatus(200, moved_to=moved)})
    assert finding.severity == Severity.INFO
    assert moved in finding.message
    fix = finding.fix
    assert (fix.line, fix.before, fix.after) == (2, f"{URL}#part", f"{moved}#part")
    assert (fix.destination.path, fix.destination.url) == (
        "docs/Notes.md",
        f"{moved}#part",
    )


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("http://example.com/a", "https://example.com/a"),
        ("https://example.com/a", "https://example.com/a/"),
        ("https://example.com/a/", "https://example.com/a"),
        ("https://example.com/", "https://www.example.com/"),
        ("https://www.example.com/", "https://example.com/"),
    ],
    ids=["https", "add-slash", "drop-slash", "add-www", "drop-www"],
)
def test_trivial_moves_are_not_reported(tmp_path, old, new):
    make_page(tmp_path, f"[it]({old})\n")
    assert check(tmp_path, {old: LinkStatus(200, moved_to=new)})[0] == []


def test_a_move_to_a_dead_page_is_reported_as_dead(tmp_path):
    make_page(tmp_path, f"[it]({URL})\n")
    [finding], _ = check(
        tmp_path, {URL: LinkStatus(404, moved_to="https://example.com/gone")}
    )
    assert finding.severity == Severity.ERROR
    assert finding.fix is None


def test_each_address_is_asked_about_once_without_its_fragment(tmp_path):
    make_page(tmp_path, f"[a]({URL}#one) [b]({URL}#two)\n[c]({URL})\n")
    findings, look_up = check(tmp_path, {URL: LinkStatus(404)})
    assert look_up.asked == [[URL]]
    assert [f.line for f in findings] == [1, 1, 2]


def test_progress_reports_go_to_the_look_up(tmp_path):
    make_page(tmp_path, f"[it]({URL})\n")
    look_up = FakeLookUp()
    reports = []
    check_external_links(tmp_path, SITE, look_up, reports.append)
    assert look_up.progress == reports.append


@pytest.mark.parametrize(
    "target",
    [
        f"{SITE}Labs/Lab01.html",
        "http://localhost:8000/admin",
        "http://127.0.0.1:5000/",
        "Labs/Lab01.md",
        "mailto:someone@example.com",
        "ftp://files.example.com/x",
    ],
)
def test_addresses_this_check_does_not_own_are_not_asked_about(tmp_path, target):
    make_page(tmp_path, f"[it]({target})\n")
    findings, look_up = check(tmp_path)
    assert findings == []
    assert look_up.asked in ([], [[]])


def test_the_course_link_checker_exclusions_are_followed(tmp_path):
    (tmp_path / ".lycheeignore").write_text(
        "# Works in a browser\n^https://gemini\\.google\\.com/$\n\n[not a regex\n",
        encoding="utf-8",
    )
    (tmp_path / "lychee.toml").write_text(
        'accept = [200, 403]\nexclude = ["chatgpt\\\\.com"]\n', encoding="utf-8"
    )
    make_page(
        tmp_path,
        "[a](https://gemini.google.com/)\n[b](https://chatgpt.com/)\n"
        "[c](https://gemini.google.com/app)\n",
    )
    _, look_up = check(tmp_path)
    assert look_up.asked == [["https://gemini.google.com/app"]]


def test_html_pages_are_checked_too(tmp_path):
    make_page(tmp_path, f'<p>\n<a href="{URL}">it</a>\n</p>\n', name="index.html")
    [finding], _ = check(tmp_path, {URL: LinkStatus(404)})
    assert (finding.path, finding.line) == ("docs/index.html", 2)


def test_no_network_means_nothing_is_reported(tmp_path):
    make_page(tmp_path, f"[it]({URL})\n")
    assert check_external_links(tmp_path, SITE, None) == []


def test_no_answer_from_anywhere_means_offline(tmp_path):
    urls = [f"https://site{n}.example/" for n in range(3)]
    make_page(tmp_path, "".join(f"[x]({url})\n" for url in urls))
    down = LinkStatus(None, error="getaddrinfo failed")
    with pytest.raises(OfflineError):
        check(tmp_path, dict.fromkeys(urls, down))


def test_a_few_unanswered_addresses_are_not_offline(tmp_path):
    urls = [f"https://site{n}.example/" for n in range(2)]
    make_page(tmp_path, "".join(f"[x]({url})\n" for url in urls))
    down = LinkStatus(None, error="getaddrinfo failed")
    findings, _ = check(tmp_path, dict.fromkeys(urls, down))
    assert len(findings) == 2


def test_findings_are_in_file_and_line_order(tmp_path):
    gone = LinkStatus(404)
    make_page(tmp_path, f"[x]({URL})\n\n[y]({URL})\n", name="B.md")
    make_page(tmp_path, f"[z]({URL})\n", name="A.md")
    findings, _ = check(tmp_path, {URL: gone})
    assert [(f.path, f.line) for f in findings] == [
        ("docs/A.md", 1),
        ("docs/B.md", 1),
        ("docs/B.md", 3),
    ]


def test_no_docs_folder_means_no_findings(tmp_path):
    assert check(tmp_path)[0] == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
