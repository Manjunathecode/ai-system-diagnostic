"""Windows-aware filesystem safety predicates for controlled cleanup."""
from __future__ import annotations

import stat
from pathlib import Path


def is_reparse_point(path: Path) -> bool:
    """Return True for symlinks, junctions, and other Windows reparse entries."""
    try:
        if path.is_symlink():
            return True
        junction = getattr(path, "is_junction", None)
        if callable(junction) and junction():
            return True
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except OSError:
        # An entry that cannot be safely classified must not be followed or deleted.
        return True
