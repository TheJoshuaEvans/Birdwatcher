"""
Contract tests for birdwatcher.report.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import html
import re
import sys
from datetime import UTC, datetime

import pytest

from birdwatcher.checks import Check
from birdwatcher.findings import Finding, Severity
from birdwatcher.report import anchor_id, stub_path, write_report
from birdwatcher.run import CheckResult, RunResult

REPO = "lcc-cit/CS212-CourseMaterials"
COMMIT = "abcdef1234" + "0" * 30


def check(check_id, title, description="Looks for things."):
    return Check(
        id=check_id, title=title, description=description, run=lambda context: []
    )


def finding(
    path, line, message="Something is off.", severity=Severity.ERROR, check_id="links"
):
    return Finding(
        check=check_id, severity=severity, path=path, line=line, message=message
    )


def make_run(results, stale=False):
    return RunResult(
        REPO, COMMIT, False, stale, datetime(2026, 11, 10, 9, 41, tzinfo=UTC), results
    )


FINDINGS = (
    finding("docs/A.md", 3),
    finding("docs/A.md", 9, "Second <problem> & more.", Severity.WARNING),
    finding("docs/Sub/B.md", None, "Whole-file issue."),
)
RUN = make_run((CheckResult(check("links", "Broken section links"), FINDINGS, 0.25),))


def read_all(out_dir):
    return {
        p.relative_to(out_dir).as_posix(): p.read_text(encoding="utf-8")
        for p in out_dir.rglob("*.html")
    }


def test_writes_an_index_and_one_stub_per_finding(tmp_path):
    index = write_report(RUN, tmp_path / "report")
    assert index == tmp_path / "report" / "index.html"
    assert index.is_file()
    for item in FINDINGS:
        assert (
            stub_path(tmp_path / "report", item)
            == tmp_path / "report" / "go" / f"{item.id}.html"
        )
        assert stub_path(tmp_path / "report", item).is_file()


def test_anchor_id_prefixes_the_finding_id():
    assert anchor_id(FINDINGS[0]) == f"f-{FINDINGS[0].id}"


def test_every_finding_has_an_anchor_and_its_source_link(tmp_path):
    page = write_report(RUN, tmp_path).read_text(encoding="utf-8")
    for item in FINDINGS:
        assert f'id="{anchor_id(item)}"' in page
        assert html.escape(RUN.source_url(item)) in page


def test_stubs_redirect_to_their_finding_by_relative_link(tmp_path):
    write_report(RUN, tmp_path)
    for item in FINDINGS:
        stub = stub_path(tmp_path, item).read_text(encoding="utf-8")
        target = f"../index.html#{anchor_id(item)}"
        assert f"location.replace({target!r})" in stub.replace('"', "'")
        assert f'url={target}"' in stub
        assert f'href="{target}"' in stub


def test_course_text_is_escaped(tmp_path):
    nasty = finding("docs/<x>.md", 1, '<script>alert("hi")</script>')
    run = make_run((CheckResult(check("links", "Links"), (nasty,), 0.1),))
    page = write_report(run, tmp_path).read_text(encoding="utf-8")
    assert "<script>alert" not in page
    assert "&lt;script&gt;alert" in page
    assert "docs/&lt;x&gt;.md" in page


def test_report_is_portable_and_self_contained(tmp_path):
    out_dir = tmp_path / "report"
    write_report(RUN, out_dir)
    for name, text in read_all(out_dir).items():
        assert "file:" not in text, name
        assert str(tmp_path) not in text and tmp_path.as_posix() not in text, name
        loads_remote = re.search(
            r"<(?:script|link|img|iframe)\b[^>]*\b(?:src|href)=\"(?:https?:)?//", text
        )
        assert loads_remote is None, name


def test_summary_describes_the_run_and_each_check(tmp_path):
    failed = CheckResult(
        check("broken", "Broken check"), (), 0.01, error="ValueError: boom"
    )
    run = make_run((RUN.results[0], failed))
    page = write_report(run, tmp_path).read_text(encoding="utf-8")
    assert REPO in page
    assert COMMIT[:7] in page
    assert f"https://github.com/{REPO}/commit/{COMMIT}" in page
    assert "Broken section links" in page and "Looks for things." in page
    assert "ValueError: boom" in page
    assert "2026-11-10" in page


def test_stale_copy_is_flagged(tmp_path):
    fresh = write_report(RUN, tmp_path / "fresh").read_text(encoding="utf-8")
    stale = write_report(
        make_run(RUN.results, stale=True), tmp_path / "stale"
    ).read_text(encoding="utf-8")
    assert "out of date" not in fresh
    assert "out of date" in stale


def test_no_findings_still_writes_a_report(tmp_path):
    run = make_run((CheckResult(check("links", "Links"), (), 0.1),))
    page = write_report(run, tmp_path).read_text(encoding="utf-8")
    assert "No findings" in page
    assert not list((tmp_path / "go").glob("*.html"))


def test_rewriting_removes_stale_stubs_but_keeps_other_files(tmp_path):
    write_report(RUN, tmp_path)
    (tmp_path / "notes.txt").write_text("mine", encoding="utf-8")
    smaller = make_run((CheckResult(check("links", "Links"), FINDINGS[:1], 0.1),))
    write_report(smaller, tmp_path)
    assert sorted(p.name for p in (tmp_path / "go").iterdir()) == [
        f"{FINDINGS[0].id}.html"
    ]
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "mine"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
