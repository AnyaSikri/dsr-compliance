"""IB (Investigator's Brochure) PDF to section index.

Extracts sections from an IB PDF using the document's Table of Contents
(TOC) for section boundaries, then extracts text page-by-page.  Falls
back to regex-based detection if no TOC is present.

No API calls — pure local extraction.
"""

from __future__ import annotations

import re
from pathlib import Path

import fitz  # PyMuPDF

from .models import DSRSection
from .pdf_extractor import _detect_sections
from .utils import logger


def _sections_to_index(sections: list[DSRSection]) -> dict[str, str]:
    """Convert a list of DSRSection objects to a ``{section_num: content}`` dict.

    If duplicate ``section_num`` values exist the *last* entry wins.

    Parent sections whose own content is empty are backfilled with the
    concatenated content of their immediate children (e.g. if "2.3" is
    empty, it gets the combined text of "2.3.1", "2.3.2", etc.).
    """
    index: dict[str, str] = {}
    for section in sections:
        index[section.section_num] = section.content

    # Backfill empty parent sections with child content
    all_nums = sorted(index.keys(), key=lambda x: [int(p) for p in x.split(".")])
    for num in all_nums:
        if index[num].strip():
            continue
        prefix = num + "."
        child_parts = [
            index[child]
            for child in all_nums
            if child.startswith(prefix) and index[child].strip()
        ]
        if child_parts:
            index[num] = "\n\n".join(child_parts)

    return index


_SECTION_NUM_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(.+)")


def _extract_via_toc(
    toc: list,
    pages: list[str],
) -> list[DSRSection]:
    """Use the PDF TOC to identify section boundaries and extract content.

    Each TOC entry has (level, title, page_number). We use page numbers
    to slice content between consecutive section starts.
    """
    # Parse TOC entries into (section_num, title, page_index) triples
    entries: list[tuple[str, str, int]] = []
    for _level, raw_title, page_num in toc:
        m = _SECTION_NUM_RE.match(raw_title.strip())
        if m:
            section_num = m.group(1)
            title = m.group(2).strip()
            # TOC page numbers are 1-indexed
            page_idx = max(page_num - 1, 0)
            entries.append((section_num, title, page_idx))

    if not entries:
        return []

    logger.info("Parsed %d numbered TOC entries from IB", len(entries))

    sections: list[DSRSection] = []
    total_pages = len(pages)

    for i, (section_num, title, start_page) in enumerate(entries):
        # End page is the start of the next section (exclusive), or end of doc.
        # Use at least start_page + 1 so sections that share a page with the
        # next section still capture the page they start on.
        if i + 1 < len(entries):
            end_page = max(entries[i + 1][2], start_page + 1)
        else:
            end_page = total_pages

        # Collect text from all pages in this section's range
        section_text_parts: list[str] = []
        for p in range(start_page, min(end_page, total_pages)):
            section_text_parts.append(pages[p])
        content = "\n".join(section_text_parts)

        sections.append(DSRSection(
            section_num=section_num,
            title=title,
            heading_full=f"{section_num} {title}",
            page_start=start_page + 1,
            page_end=end_page,
            file="",
            content=content,
        ))

    return sections


def build_ib_index(ib_pdf_path: Path) -> dict[str, str]:
    """Extract an IB PDF and return a section-number-to-content index.

    Uses the document TOC as the primary section detection method, since
    IB PDFs often have section numbers and titles on separate lines which
    breaks regex-based heading detection.  Falls back to regex if no TOC.

    No API calls are made.
    """
    logger.info("Building IB index from: %s", ib_pdf_path.name)

    doc = fitz.open(str(ib_pdf_path))
    pages: list[str] = [page.get_text("text") for page in doc]
    toc = doc.get_toc()
    doc.close()
    logger.info("Extracted %d pages from IB", len(pages))

    if toc:
        logger.info("IB has TOC with %d entries — using TOC-based extraction", len(toc))
        sections = _extract_via_toc(toc, pages)
    else:
        logger.info("No TOC found — falling back to regex-based extraction")
        sections = _detect_sections(pages, set())

    logger.info("Detected %d sections in IB", len(sections))

    index = _sections_to_index(sections)
    logger.info("IB index built with %d entries", len(index))

    return index
