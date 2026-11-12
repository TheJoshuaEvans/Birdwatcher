"""
Refresh Birdwatcher's built-in word lists from the dictionaries VS Code's Code
Spell Checker uses (the MIT-licensed @cspell/dict-* packages on npm).

For each package it reads only the word lists (*.txt and *.txt.gz, in dict/
or at the top) and the LICENSE out of the published archive, and writes
birdwatcher/checks/words/<name>.txt (one word per line, sorted, comments and
compound-word affix entries left out) and words/licenses/<name>.txt, then
lists the packages and versions in words/README.md.

Run from the repository root:  uv run python tools/update_word_lists.py

Joshua Evans, 2026-11-12 (written with Claude Opus 5.5)
"""

import gzip
import io
import json
import tarfile
import urllib.request
from pathlib import Path

PACKAGES = (
    "software-terms",
    "python",
    "node",
    "typescript",
    "html",
    "css",
    "fullstack",
    "companies",
    "data-science",
    "filetypes",
)
REGISTRY = "https://registry.npmjs.org/@cspell%2fdict-{name}/latest"
WORDS = Path(__file__).resolve().parent.parent / "birdwatcher" / "checks" / "words"
USER_AGENT = "Birdwatcher word list updater"


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def words_from(text):
    """The words of a cspell word list: no comments, no affix entries."""
    for line in text.splitlines():
        word = line.strip()
        if word and not word.startswith("#") and "*" not in word and "!" not in word:
            yield word.lstrip("~+")


def read_package(tarball):
    """(words, license text) from a package archive; only those files are read."""
    words, license_text = set(), ""
    with tarfile.open(fileobj=io.BytesIO(tarball)) as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            if member.name == "package/LICENSE":
                license_text = archive.extractfile(member).read().decode("utf-8")
            # Word lists sit in dict/, or at the top of some packages
            elif member.name.startswith("package/dict/") or member.name.count("/") == 1:
                data = archive.extractfile(member).read()
                if member.name.endswith(".txt.gz"):
                    data = gzip.decompress(data)
                elif not member.name.endswith(".txt"):
                    continue
                words.update(words_from(data.decode("utf-8")))
    return words, license_text


def main():
    (WORDS / "licenses").mkdir(parents=True, exist_ok=True)
    rows = []
    for name in PACKAGES:
        latest = json.loads(fetch(REGISTRY.format(name=name)))
        words, license_text = read_package(fetch(latest["dist"]["tarball"]))
        (WORDS / f"{name}.txt").write_text(
            "\n".join(sorted(words, key=str.lower)) + "\n", encoding="utf-8"
        )
        (WORDS / "licenses" / f"{name}.txt").write_text(license_text, encoding="utf-8")
        rows.append((name, latest["version"], latest.get("license", "?"), len(words)))
        print(
            f"{name}: {len(words)} words (v{latest['version']}, {latest.get('license')})"
        )
    readme = [
        "# Built-in word lists",
        "",
        "Words the spelling check knows in every course, from the dictionaries VS Code's",
        "Code Spell Checker uses: the `@cspell/dict-*` packages on npm, by Street Side",
        "Software, under the MIT license (each package's license is in `licenses/`).",
        "Refresh them with `uv run python tools/update_word_lists.py`.",
        "",
        "`birdwatcher.txt` is kept by hand, for words those dictionaries miss that",
        "any course might use (libraries, data science, everyday tech words); the",
        "refresh leaves it alone. Names and a course's own terms belong in that",
        "course's `cspell.json` instead.",
        "",
        "| Package | Version | License | Words |",
        "|---|---|---|---|",
        *(f"| @cspell/dict-{n} | {v} | {lic} | {count} |" for n, v, lic, count in rows),
        "",
    ]
    (WORDS / "README.md").write_text("\n".join(readme), encoding="utf-8")


if __name__ == "__main__":
    main()
