"""
Dead links: links and images in the site's pages that lead nowhere.

The site is published from docs/ by GitHub Pages, which runs on Linux, so a
path whose letter case differs from the file's works on Windows and macOS
but is broken on the site.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import difflib
import re
import urllib.parse
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from birdwatcher.checks.pages import page_links, read_page, site_pages
from birdwatcher.core.course import DOCS_FOLDER
from birdwatcher.core.findings import Destination, Finding, Fix, Severity

CHECK = "dead-link"
SUGGESTION_CUTOFF = 0.75  # difflib similarity needed to suggest an existing file
INDEX_NAMES = ("index.md", "index.html", "README.md")  # what a folder's address shows
URL_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


@dataclass(frozen=True)
class _Resolved:
    """Where a target leads: the file it shows (None when it leads nowhere),
    the target's path spelled with the names' real letter case, and for a
    dead end, the folder and name where it stopped."""

    file: Path | None
    spelled: str
    case_differs: bool = False
    stopped_in: Path | None = None
    missing: str | None = None


def check_links(repo_root, site_url):
    """
    Find links and images in the site's Markdown and HTML pages that lead to
    nothing inside the site.

    A target is inside the site when it is a relative path, a path starting
    with the site's own path (e.g. "/CS212-CourseMaterials/..."), or a full
    address starting with site_url. Its "#section" and "?query" are ignored
    (broken sections are check_anchors' job). It resolves against the page's
    folder (or docs/ for the site's own addresses) and exists when, with the
    exact letter case of every name on the way:

    - it names a file;
    - it names a folder (or ends in "/") holding index.md, index.html or
      README.md;
    - it names a .html page whose .md source exists; or
    - it has no extension and a .md or .html page of that name exists.

    Other targets (other sites, "#section" alone, mailto: and other schemes,
    other root paths, and everything when site_url is None and the target is
    a full address) are not checked here.

    Args:
        repo_root (Path): Root folder of the course repository.
        site_url (str | None): Published site address ending in "/", as from
            core.course.published_site_url, or None when it is not known.

    Returns:
        list[Finding]: In file and line order, one error per dead target:
            - outside docs/: says it leads outside the published site;
            - existing only in a different letter case: names the file as it
              is spelled, with a Fix replacing the target with the same
              target spelled that way, whose destination is that file;
            - missing: says so, naming a file in the same folder with a
              close name when there is one ("Did you mean ...?").
            Empty when the repository has no docs/ folder.
    """
    repo_root = Path(repo_root).resolve()
    docs = repo_root / DOCS_FOLDER
    if not docs.is_dir():
        return []
    site_path = urllib.parse.urlsplit(site_url).path if site_url else None

    @cache
    def names_in(folder):
        return (
            tuple(child.name for child in folder.iterdir()) if folder.is_dir() else ()
        )

    findings = []
    for page in site_pages(docs, suffixes=(".md", ".html")):
        is_html = page.suffix.lower() == ".html"
        for line, target in page_links(read_page(page), html=is_html):
            finding = _check_target(
                page, line, target, docs, repo_root, site_url, site_path, names_in
            )
            if finding is not None:
                findings.append(finding)
    return sorted(findings, key=lambda finding: (finding.path, finding.line))


def _check_target(page, line, target, docs, repo_root, site_url, site_path, names_in):
    """The finding for one link target, or None when it is fine or not ours."""
    if site_url and target.startswith(site_url):
        base, prefix = docs, site_url
    elif site_path and target.startswith(site_path):
        base, prefix = docs, site_path
    elif URL_SCHEME.match(target) or target.startswith(("/", "#")):
        return None
    else:
        base, prefix = page.parent, ""
    rest = target[len(prefix) :]
    path = re.split(r"[?#]", rest, maxsplit=1)[0]
    tail = rest[len(path) :]
    if not path:
        return None

    def report(message, fix=None):
        return Finding(
            check=CHECK,
            severity=Severity.ERROR,
            path=page.relative_to(repo_root).as_posix(),
            line=line,
            message=message,
            fix=fix,
        )

    if not (base / urllib.parse.unquote(path)).resolve().is_relative_to(docs):
        return report(
            f"Link '{target}' leads outside the published site (docs/), so it is "
            "broken on the site."
        )
    resolved = _resolve(base, path, names_in)
    if resolved.file is None:
        message = f"Link '{target}' leads to "
        if resolved.missing is None:
            message += (
                "a folder with no index page (index.md, index.html or README.md), "
                "which the site shows as not found."
            )
        else:
            message += "a file that does not exist."
            names = names_in(resolved.stopped_in)
            if resolved.missing.lower().endswith(".html"):  # offer the published name
                names = [_published_name(name) for name in names]
            close = difflib.get_close_matches(
                resolved.missing,
                names,
                n=1,
                cutoff=SUGGESTION_CUTOFF,
            )
            if close:
                message += f" Did you mean '{close[0]}'?"
        return report(message)
    if resolved.case_differs:
        after = prefix + resolved.spelled + tail
        return report(
            f"Link '{target}' works on Windows and macOS but is broken on the "
            f"published site, where letter case matters: it is spelled '{after}'.",
            Fix(
                line=line,
                before=target,
                after=after,
                destination=Destination(
                    path=resolved.file.relative_to(repo_root).as_posix(),
                    line=None,
                    url=None,
                ),
            ),
        )
    return None


def _published_name(name):
    """A file's name on the site: a .md page is published as .html."""
    stem, dot, suffix = name.rpartition(".")
    return f"{stem}.html" if dot and suffix.lower() == "md" else name


def _resolve(base, path, names_in):
    """Follow a link path from base, one name at a time, matching letter case
    exactly where it can and ignoring it where it must."""
    folder = base
    segments = path.split("/")
    spelled = []
    case_differs = False
    for index, segment in enumerate(segments):
        name = urllib.parse.unquote(segment)
        last = index == len(segments) - 1
        if name in ("", "."):
            spelled.append(segment)
            if last:
                return _folder_index(folder, "/".join(spelled), case_differs, names_in)
            continue
        if name == "..":
            folder = folder.parent
            spelled.append(segment)
            continue
        found = _find(folder, name, last, names_in)
        if found is None:
            return _Resolved(None, "", stopped_in=folder, missing=name)
        real, shown = found
        case_differs = case_differs or shown != name
        spelled.append(urllib.parse.quote(shown) if "%" in segment else shown)
        folder = folder / real
        if last:
            if folder.is_dir():
                return _folder_index(folder, "/".join(spelled), case_differs, names_in)
            return _Resolved(folder, "/".join(spelled), case_differs)
    return _Resolved(None, "", stopped_in=folder, missing=segments[-1])


def _find(folder, name, last, names_in):
    """(the real name to follow, the name the link should spell) for one name
    in a folder, or None. The last name of a path may also mean a page: x.html
    for its source x.md, and x for x.md or x.html."""
    options = [(name, "")]
    if last:
        stem, dot, suffix = name.rpartition(".")
        if dot and suffix.lower() == "html":
            options.append((f"{stem}.md", ".html"))
        elif not dot:
            options += [(f"{name}.md", ""), (f"{name}.html", "")]
    names = names_in(folder)
    for exact in (True, False):
        for wanted, keep in options:
            for real in names:
                same = (real == wanted) if exact else (real.lower() == wanted.lower())
                if same:
                    shown = real
                    if wanted != name:  # a page found for the name: keep its form
                        shown = real.rpartition(".")[0] + keep
                    return real, shown
    return None


def _folder_index(folder, spelled, case_differs, names_in):
    """A folder leads to its index page, if it has one."""
    names = names_in(folder)
    index = next((name for name in INDEX_NAMES if name in names), None)
    if index is None:
        return _Resolved(None, spelled)
    return _Resolved(folder / index, spelled, case_differs)
