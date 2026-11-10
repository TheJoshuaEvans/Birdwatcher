"""
The HTML report: a self-contained, portable folder that opens from disk or a web host.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from itertools import groupby
from pathlib import Path

from jinja2 import Environment, PackageLoader

from birdwatcher.findings import Finding, Severity

INDEX_FILE = "index.html"
STUB_FOLDER = "go"
PROJECT_URL = "https://github.com/TheJoshuaEvans/Birdwatcher"
SHORT_COMMIT = 7
SEVERITY_LABELS = {
    Severity.ERROR: ("Error", "errors"),
    Severity.WARNING: ("Warning", "warnings"),
    Severity.INFO: ("Info", "info"),
}

_templates = Environment(
    loader=PackageLoader("birdwatcher", "templates"),
    autoescape=True,  # course text is full of HTML; it must never become markup
    trim_blocks=True,
    lstrip_blocks=True,
)


def anchor_id(finding):
    """
    Return the HTML id of a finding's entry in the report.

    Args:
        finding (Finding): A finding.

    Returns:
        str: "f-" followed by the finding's id.
    """
    return f"f-{finding.id}"


def stub_path(out_dir, finding):
    """
    Return where a finding's redirect page is written.

    Opening that page shows the report scrolled to the finding. It exists because
    Windows drops the "#..." part of file:// links opened from a terminal.

    Args:
        out_dir (Path): The report folder.
        finding (Finding): A finding.

    Returns:
        Path: out_dir / "go" / "<finding id>.html".
    """
    return Path(out_dir) / STUB_FOLDER / f"{finding.id}.html"


def write_report(run, out_dir):
    """
    Write the HTML report for a run.

    Writes index.html (summary, every check with its description, finding count
    and any error, and every finding grouped by file, each with its source link
    on GitHub) and one redirect page per finding (see stub_path). The pages load
    nothing from the network, link to each other only by relative paths, contain
    no local file paths, and escape all course text. Stale redirect pages from
    earlier reports are removed; other files in out_dir are left alone.

    Args:
        run (RunResult): What to report.
        out_dir (Path): Report folder; created if missing.

    Returns:
        Path: The written index.html.
    """
    out_dir = Path(out_dir)
    stubs = out_dir / STUB_FOLDER
    stubs.mkdir(parents=True, exist_ok=True)
    for old in stubs.glob("*.html"):
        old.unlink()

    findings = run.findings
    stub = _templates.get_template("stub.html.j2")
    for finding in findings:
        target = f"../{INDEX_FILE}#{anchor_id(finding)}"
        stub_path(out_dir, finding).write_text(
            stub.render(target=target), encoding="utf-8"
        )

    page = _templates.get_template("report.html.j2").render(
        run=run,
        short_commit=run.commit[:SHORT_COMMIT],
        commit_url=f"https://github.com/{run.repo}/commit/{run.commit}",
        checked_at=run.started_at.strftime("%Y-%m-%d %H:%M UTC"),
        totals=_totals(run),
        checks=_check_rows(run),
        groups=_groups(run, findings),
        project_url=PROJECT_URL,
    )
    index = out_dir / INDEX_FILE
    index.write_text(page, encoding="utf-8")
    return index


def _totals(run):
    """Non-zero counts per severity, most severe first."""
    totals = []
    for severity, (label, plural) in SEVERITY_LABELS.items():
        count = run.count(severity)
        if count:
            word = label.lower() if count == 1 else plural
            totals.append(
                {
                    "severity": severity.value,
                    "count": count,
                    "label": word,
                    "label_plural": plural.capitalize(),
                }
            )
    return totals


def _check_rows(run):
    return [
        {
            "id": result.check.id,
            "title": result.check.title,
            "description": result.check.description,
            "count": len(result.findings),
            "seconds": f"{result.seconds:.2f} s",
            "error": result.error,
        }
        for result in run.results
    ]


def _groups(run, findings):
    """Findings grouped by file, in the run's order."""
    titles = {result.check.id: result.check.title for result in run.results}
    groups = []
    for path, items in groupby(findings, key=lambda finding: finding.path):
        entries = [
            {
                "anchor": anchor_id(finding),
                "severity": finding.severity.value,
                "severity_label": SEVERITY_LABELS[finding.severity][0],
                "line": finding.line,
                "source_url": run.source_url(finding),
                "check_title": titles.get(finding.check, finding.check),
                "message": finding.message,
            }
            for finding in items
        ]
        file_url = run.source_url(_whole_file(path))
        groups.append({"path": path, "url": file_url, "entries": entries})
    return groups


def _whole_file(path):
    """A stand-in finding for linking to a file without a line."""
    return Finding(check="", severity=Severity.INFO, path=path, line=None, message="")
