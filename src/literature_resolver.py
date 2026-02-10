"""Clinical literature reference loader.

Supports manual reference files (JSON) for Medline, Embase, UpToDate.
Full database API integration can be added in a later phase.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .utils import logger


def load_literature_index(literature_path: Optional[Path] = None) -> dict[str, str]:
    """Load literature references from a JSON file.

    Expected format::

        {
            "Medline": "Summary of Medline search results...",
            "Embase": "Summary of Embase findings...",
            "UpToDate": "Clinical summary from UpToDate..."
        }

    Returns a dict mapping reference keywords to content strings.
    Returns an empty dict if no file is provided or loading fails.
    """
    if literature_path is None or not literature_path.exists():
        logger.info("No literature index provided — external refs will be placeholders")
        return {}

    try:
        data = json.loads(literature_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            logger.warning("Literature index is not a dict — ignoring")
            return {}
        logger.info("Loaded %d literature entries from %s", len(data), literature_path.name)
        return data
    except Exception as e:
        logger.warning("Failed to load literature index: %s", e)
        return {}
