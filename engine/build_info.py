"""Single source of truth for the app's build identifier.

The build label is bumped on every meaningful code change, and every output the
app produces (Excel ``Run_Metadata``, PDF cover, deck date footer, sidebar
badge) carries this same label. Two runs that disagree must therefore carry
different labels — solving the "is this stale?" problem that the old static
``v33`` label hid, where multiple incompatible builds shared one identifier.

Convention: bump the patch component for any code change that ships
(``v33.5`` → ``v33.6``…); bump the minor for a notable behaviour change.
"""

from __future__ import annotations

# IMPORTANT: bump this on every code change that ships.
BUILD = "v34.62"


def build_stamp() -> str:
    """Short label suitable for footers and metadata sheets (``'Build v33.5'``)."""
    return f"Build {BUILD}"
