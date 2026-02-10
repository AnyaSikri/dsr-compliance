"""PBRER (Periodic Benefit-Risk Evaluation Report) PDF extractor.

Similar to ib_extractor but for PBRER documents. Returns a
dict[str, str] mapping section numbers to content.

Reuses shared extraction functions from ib_extractor and pdf_extractor.
No API calls are made.
"""

from __future__ import annotations

from pathlib import Path

import fitz

from .ib_extractor import _extract_via_toc, _sections_to_index
from .pdf_extractor import _detect_sections, _strip_headers_footers
from .utils import logger


def build_pbrer_index(pbrer_pdf_path: Path) -> dict[str, str]:
    """Extract a PBRER PDF and return a section-number-to-content index.

    Uses the same TOC-first, regex-fallback strategy as the IB extractor.
    No API calls are made.
    """
    logger.info("Building PBRER index from: %s", pbrer_pdf_path.name)

    doc = fitz.open(str(pbrer_pdf_path))
    pages: list[str] = [page.get_text("text") for page in doc]
    toc = doc.get_toc()
    doc.close()
    logger.info("Extracted %d pages from PBRER", len(pages))

    # Strip headers/footers for cleaner extraction
    pages = _strip_headers_footers(pages)

    if toc:
        logger.info("PBRER has TOC with %d entries", len(toc))
        sections = _extract_via_toc(toc, pages)
    else:
        logger.info("No TOC found — falling back to regex-based extraction")
        sections = _detect_sections(pages, set())

    logger.info("Detected %d sections in PBRER", len(sections))

    index = _sections_to_index(sections)
    logger.info("PBRER index built with %d entries", len(index))

    return index
