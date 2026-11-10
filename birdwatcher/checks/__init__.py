"""
The checks: one module per check, and ALL_CHECKS, the registry of every check
Birdwatcher runs, in display order.

A check module exposes a CHECK id and a function that takes what it needs from
a core.check.CheckContext and returns a list of core.findings.Finding. Adding a
check means a new module here, an entry in ALL_CHECKS, and a line in the
README's checklist.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from birdwatcher.checks import anchors, numbering
from birdwatcher.core.check import Check

ALL_CHECKS = (
    Check(
        id=anchors.CHECK,
        title="Broken section links",
        description=(
            "Links to a #section that does not exist on the target page. Readers who "
            "click them land at the top of the page instead of the section. The "
            "site's link checker does not look at the part after '#'."
        ),
        run=lambda context: anchors.check_anchors(context.root, context.site_url),
    ),
    Check(
        id=numbering.CHECK,
        title="Renumbering leftovers",
        description=(
            "Lab files named for a different lab or group than the folder they are "
            "in, and lab folders that share a number. They are usually copies left "
            "behind when labs were renumbered or reorganised, and students may "
            "open the wrong one."
        ),
        run=lambda context: numbering.check_numbering(context.root),
    ),
)
