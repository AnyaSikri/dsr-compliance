"""Utility functions: scope parsing, filename sanitization, logging setup."""

from __future__ import annotations

import logging
import re
from pathlib import Path


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure and return the package logger."""
    logger = logging.getLogger("dsr_compliance")
    if not logger.handlers:
        handler = logging.StreamHandler()
        fmt = "%(asctime)s [%(levelname)s] %(message)s"
        handler.setFormatter(logging.Formatter(fmt, datefmt="%H:%M:%S"))
        logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    return logger


logger = setup_logging()


# ---------------------------------------------------------------------------
# Dotted-decimal section number utilities
# ---------------------------------------------------------------------------

def _parse_section_num(s: str) -> tuple[int, ...]:
    """Parse '1.2.3' into (1, 2, 3). Returns empty tuple for non-numeric."""
    s = s.strip()
    if not s:
        return ()
    parts = s.split(".")
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return ()


def _section_le(a: tuple[int, ...], b: tuple[int, ...]) -> bool:
    """True if section a <= section b in dotted-decimal ordering."""
    for x, y in zip(a, b):
        if x < y:
            return True
        if x > y:
            return False
    return len(a) <= len(b)


def parse_scope(scope_str: str) -> tuple[tuple[int, ...], tuple[int, ...]] | None:
    """Parse a scope string like '1.1-1.2.2.4' into (start, end) tuples.

    Returns None if the scope string is empty or unparseable.
    """
    scope_str = scope_str.strip()
    if not scope_str:
        return None
    parts = scope_str.split("-", 1)
    if len(parts) != 2:
        return None
    start = _parse_section_num(parts[0])
    end = _parse_section_num(parts[1])
    if not start or not end:
        return None
    return start, end


def section_in_scope(section_num: str, scope: tuple[tuple[int, ...], tuple[int, ...]] | None) -> bool:
    """Check whether a section number falls within the given scope range.

    Uses >= / <= comparison on dotted-decimal tuples. A section like 1.2.2
    is in scope of 1.1-1.2.2.4 because (1,2,2) >= (1,1) and (1,2,2) <= (1,2,2,4).
    """
    if scope is None:
        return True  # no scope = everything in scope
    parsed = _parse_section_num(section_num)
    if not parsed:
        return False
    start, end = scope
    return _section_le(start, parsed) and _section_le(parsed, end)


def sanitize_filename(name: str, max_len: int = 80) -> str:
    """Convert a section title to a safe filename component."""
    name = re.sub(r"[^\w\s\-]", "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:max_len]


def ensure_dir(path: Path) -> Path:
    """Create directory (and parents) if it doesn't exist, return path."""
    path.mkdir(parents=True, exist_ok=True)
    return path
