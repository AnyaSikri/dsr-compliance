"""PDF mode: PyMuPDF extraction + regex-based section splitting.

Extracts text page-by-page, detects section boundaries using a heading
regex, and writes individual .md files + an index CSV to
data/intermediate/. Uses an optional API call only for ambiguous pages.

Enhanced with:
- pdfplumber table extraction
- Header/footer stripping
- OCR fallback for scanned pages
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter
from pathlib import Path

import fitz  # PyMuPDF
import pdfplumber

from .config import Config
from .models import DSRSection
from .openai_client import LLMClient
from .utils import ensure_dir, logger, sanitize_filename

# Regex for section headings: dotted-decimal number followed by title in caps/mixed
# Must be hierarchical (contain at least one dot) OR be a single top-level number (1-9)
HEADING_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)*)\s+([A-Z][A-Za-z\s\-:,\u2013\u2014()]+)",
    re.MULTILINE,
)

# Section numbers that are clearly not real headings (standalone low numbers
# that appear in table data, case narratives, etc.)
_WHITELIST_STANDALONE = {"1", "2", "3", "4", "5", "6", "7"}


def _is_valid_section_num(num: str, title: str) -> bool:
    """Heuristic: is this a real section heading?"""
    # Hierarchical numbers (e.g. 1.2, 3.3.1) are always valid
    if "." in num:
        return True
    # Single-digit top-level sections are valid only if the title
    # looks like a proper heading (mostly uppercase, reasonable length)
    if num in _WHITELIST_STANDALONE:
        stripped = title.strip()
        if len(stripped) < 3:
            return False
        # Must have at least some uppercase letters
        upper_ratio = sum(1 for c in stripped if c.isupper()) / max(len(stripped), 1)
        return upper_ratio > 0.3 and len(stripped) > 5
    return False


def _extract_tables(pdf_path: Path) -> list[list[list[str]]]:
    """Extract all tables from a PDF using pdfplumber.

    Returns a list of tables, each table being a list of rows,
    each row being a list of cell strings.
    """
    tables: list[list[list[str]]] = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                page_tables = page.extract_tables()
                if page_tables:
                    for table in page_tables:
                        # Normalize None cells to empty strings
                        clean_table = [
                            [cell if cell is not None else "" for cell in row]
                            for row in table
                            if row is not None
                        ]
                        if clean_table:
                            tables.append(clean_table)
    except Exception as e:
        logger.warning("pdfplumber table extraction failed: %s", e)
    return tables


def _strip_headers_footers(
    pages: list[str], threshold: int = 3
) -> list[str]:
    """Remove repeated headers and footers from extracted pages.

    A line is considered a header/footer if it appears on at least
    *threshold* pages (compared after stripping whitespace).
    """
    if len(pages) < threshold:
        return pages

    # Collect first and last lines of each page
    first_lines: list[str] = []
    last_lines: list[str] = []
    for page in pages:
        lines = [l.strip() for l in page.split("\n") if l.strip()]
        first_lines.append(lines[0] if lines else "")
        last_lines.append(lines[-1] if lines else "")

    # Count occurrences
    header_counts = Counter(first_lines)
    footer_counts = Counter(last_lines)

    # Identify repeated headers/footers
    headers_to_strip = {
        line for line, count in header_counts.items()
        if count >= threshold and line
    }
    footers_to_strip = {
        line for line, count in footer_counts.items()
        if count >= threshold and line
    }

    if headers_to_strip:
        logger.info("Stripping %d repeated header pattern(s)", len(headers_to_strip))
    if footers_to_strip:
        logger.info("Stripping %d repeated footer pattern(s)", len(footers_to_strip))

    cleaned: list[str] = []
    for page in pages:
        lines = page.split("\n")
        filtered = []
        for line in lines:
            stripped = line.strip()
            if stripped in headers_to_strip or stripped in footers_to_strip:
                continue
            filtered.append(line)
        cleaned.append("\n".join(filtered))

    return cleaned


def _ocr_page(page: object, dpi: int = 300) -> str:
    """OCR fallback for pages with no text layer.

    Uses pytesseract to extract text from a PyMuPDF page rendered as an image.
    Returns empty string if OCR dependencies are not available.
    """
    try:
        from PIL import Image
        import pytesseract
    except ImportError:
        logger.warning("pytesseract or Pillow not installed — skipping OCR")
        return ""

    try:
        pixmap = page.get_pixmap(dpi=dpi)
        img = Image.open(io.BytesIO(pixmap.tobytes("png")))
        return pytesseract.image_to_string(img)
    except Exception as e:
        logger.warning("OCR failed for page: %s", e)
        return ""


def extract_pdf(
    pdf_path: Path,
    config: Config,
    llm: LLMClient,
) -> tuple[list[DSRSection], Path]:
    """Extract sections from a DSR PDF.

    Returns (list of DSRSection, path to index CSV).
    """
    logger.info("Extracting PDF: %s", pdf_path.name)
    doc = fitz.open(str(pdf_path))

    # --- Step 1: Extract full text page by page (with OCR fallback) ---
    pages: list[str] = []
    for page in doc:
        text = page.get_text("text")
        if len(text.strip()) < 50 and config.ocr_enabled:
            logger.debug("Page %d has little text, trying OCR", page.number + 1)
            ocr_text = _ocr_page(page)
            if ocr_text.strip():
                text = ocr_text
        pages.append(text)
    doc.close()
    logger.info("Extracted %d pages", len(pages))

    # --- Step 1b: Strip repeated headers/footers ---
    pages = _strip_headers_footers(pages)

    # --- Step 2: Optional TOC extraction for validation ---
    doc2 = fitz.open(str(pdf_path))
    toc = doc2.get_toc()
    doc2.close()
    toc_sections: set[str] = set()
    if toc:
        for level, title, page_num in toc:
            # Extract section numbers from TOC entries
            m = re.match(r"^(\d+(?:\.\d+)*)\s+", title)
            if m:
                toc_sections.add(m.group(1))
        logger.info("TOC found with %d entries for validation", len(toc_sections))

    # --- Step 3: Detect section boundaries ---
    full_text = "\n\n".join(f"===== PAGE {i+1} =====\n{p}" for i, p in enumerate(pages))
    sections = _detect_sections(pages, toc_sections)
    logger.info("Detected %d sections from regex", len(sections))

    # --- Step 4: API disambiguation for ambiguous pages ---
    if config.dry_run:
        logger.info("DRY RUN — skipping API disambiguation")
    else:
        sections = _disambiguate_if_needed(sections, pages, llm)

    # --- Step 5: Write .md files and index CSV ---
    out_dir = ensure_dir(config.intermediate_dir / "dsr_sections")
    index_path = _write_outputs(sections, out_dir)

    return sections, index_path


def _detect_sections(pages: list[str], toc_sections: set[str]) -> list[DSRSection]:
    """Regex-based section boundary detection across all pages."""
    sections: list[DSRSection] = []
    current_section: DSRSection | None = None
    current_body_lines: list[str] = []

    for page_idx, page_text in enumerate(pages):
        page_num = page_idx + 1
        lines = page_text.split("\n")

        for line in lines:
            match = HEADING_RE.match(line)
            if match:
                num = match.group(1)
                title = match.group(2).strip()

                if not _is_valid_section_num(num, title):
                    # Not a real heading, treat as body text
                    current_body_lines.append(line)
                    continue

                # If we have a TOC, validate against it
                if toc_sections and "." in num and num not in toc_sections:
                    # Hierarchical number not in TOC — might be a false positive
                    # Still accept it if it looks strongly like a heading
                    pass

                # Close previous section
                if current_section is not None:
                    current_section.content = "\n".join(current_body_lines)
                    current_section.page_end = page_num
                    sections.append(current_section)

                # Start new section
                heading_full = f"{num} {title}"
                filename = f"{num}_{sanitize_filename(title)}.md"
                current_section = DSRSection(
                    section_num=num,
                    title=title,
                    heading_full=heading_full,
                    page_start=page_num,
                    page_end=page_num,
                    file=filename,
                )
                current_body_lines = [line]
            else:
                current_body_lines.append(line)
                if current_section is not None:
                    current_section.page_end = page_num

    # Close last section
    if current_section is not None:
        current_section.content = "\n".join(current_body_lines)
        sections.append(current_section)

    return sections


API_DISAMBIG_SYSTEM = """\
You are a document structure analyst. Given text from specific pages \
of a Drug Safety Report, determine whether the identified section \
boundaries are correct. Some numbers at line starts may be table data \
or list items rather than section headings.

Return a JSON object with:
  - "corrections": a list of objects, each with:
    - "page": page number
    - "false_positive_numbers": list of numbers that look like headings \
but are actually table/list data
    - "missed_headings": list of {"num": "X.Y", "title": "..."} for \
any real section headings that were missed
"""


def _disambiguate_if_needed(
    sections: list[DSRSection],
    pages: list[str],
    llm: LLMClient,
) -> list[DSRSection]:
    """Use API to resolve ambiguous section boundaries.

    Only called for pages with suspicious patterns (many short sections,
    standalone numbers, etc.).
    """
    # Identify ambiguous pages: pages where we found multiple section
    # starts and at least one standalone (non-hierarchical) number
    page_section_counts: dict[int, int] = {}
    page_has_standalone: dict[int, bool] = {}
    for s in sections:
        for p in range(s.page_start, s.page_end + 1):
            page_section_counts[p] = page_section_counts.get(p, 0) + 1
        if "." not in s.section_num:
            page_has_standalone[s.page_start] = True

    ambiguous_pages: list[int] = []
    for page_num, count in page_section_counts.items():
        if count >= 3 and page_has_standalone.get(page_num, False):
            ambiguous_pages.append(page_num)

    if not ambiguous_pages:
        return sections

    # Limit to 15 API calls max
    ambiguous_pages = sorted(ambiguous_pages)[:15]
    logger.info("API disambiguation for %d ambiguous pages", len(ambiguous_pages))

    for page_num in ambiguous_pages:
        page_text = pages[page_num - 1] if page_num <= len(pages) else ""
        if not page_text.strip():
            continue

        try:
            result = llm.call_json(
                system_prompt=API_DISAMBIG_SYSTEM,
                user_prompt=f"Page {page_num}:\n{page_text[:3000]}",
                label=f"disambig_page_{page_num}",
            )

            false_positives = set()
            for correction in result.get("corrections", []):
                for fp in correction.get("false_positive_numbers", []):
                    false_positives.add(str(fp))

            if false_positives:
                # Remove false-positive sections
                before = len(sections)
                sections = [
                    s for s in sections
                    if not (s.page_start == page_num and s.section_num in false_positives)
                ]
                logger.info(
                    "Page %d: removed %d false-positive sections",
                    page_num, before - len(sections),
                )
        except Exception as e:
            logger.warning("API disambiguation failed for page %d: %s", page_num, e)

    return sections


def _write_outputs(sections: list[DSRSection], out_dir: Path) -> Path:
    """Write .md files and index CSV."""
    # Write .md files
    for s in sections:
        md_path = out_dir / s.file
        content = f"# {s.heading_full}\n\n**Page range:** {s.page_start}\u2013{s.page_end}\n\n"
        content += f"```text\n{s.content}\n```\n"
        md_path.write_text(content, encoding="utf-8")

    # Write index CSV
    index_path = out_dir.parent / "dsr_sections_index.csv"
    with open(index_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["section_num", "title", "heading_full", "page_start", "page_end", "file"])
        for s in sections:
            writer.writerow([
                s.section_num, s.title, s.heading_full,
                s.page_start, s.page_end, str(out_dir / s.file),
            ])

    logger.info("Written %d .md files + index to %s", len(sections), out_dir)
    return index_path
