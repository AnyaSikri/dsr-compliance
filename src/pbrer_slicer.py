"""PBRER page slicer: extract specific page ranges into a section index.

Usage:
    python -m src.pbrer_slicer \
        --pbrer data/template/pbrer.pdf \
        --pages "5:1-20, 5.1:21-45, 5.2:46-80" \
        --output data/template/pbrer_index.json

The --pages argument is a comma-separated list of section:start-end pairs.
Pages are 1-indexed. The output is a JSON file mapping section numbers to
extracted text, which can be fed to the main pipeline via --pbrer-index.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

from .utils import logger, setup_logging


def _extract_pages_markdown(pdf_path: Path, start: int, end: int) -> str:
    """Extract pages [start, end] (1-indexed) as markdown text.

    Tries pymupdf4llm first, falls back to plain PyMuPDF.
    """
    try:
        import pymupdf4llm

        page_dicts = pymupdf4llm.to_markdown(
            str(pdf_path),
            page_chunks=True,
            pages=list(range(start - 1, end)),
        )
        parts = [chunk.get("text", "") for chunk in page_dicts]
        return "\n".join(parts)
    except ImportError:
        pass
    except Exception:
        pass

    # Fallback: plain PyMuPDF
    doc = fitz.open(str(pdf_path))
    parts = []
    for i in range(start - 1, min(end, len(doc))):
        parts.append(doc[i].get_text("text"))
    doc.close()
    return "\n".join(parts)


def parse_page_spec(spec: str) -> list[tuple[str, int, int]]:
    """Parse a page specification string into (section_num, start, end) triples.

    Format: "5:1-20, 5.1:21-45, 5.2:46-80"
    """
    entries = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\d+(?:\.\d+)*)\s*:\s*(\d+)\s*-\s*(\d+)$", part)
        if not m:
            logger.warning("Skipping invalid page spec: '%s'", part)
            continue
        section_num = m.group(1)
        start = int(m.group(2))
        end = int(m.group(3))
        entries.append((section_num, start, end))
    return entries


def build_pbrer_index_from_pages(
    pdf_path: Path,
    page_specs: list[tuple[str, int, int]],
) -> dict[str, str]:
    """Build a PBRER section index by extracting specified page ranges."""
    index: dict[str, str] = {}
    for section_num, start, end in page_specs:
        logger.info("Extracting PBRER section %s (pages %d-%d)", section_num, start, end)
        text = _extract_pages_markdown(pdf_path, start, end)
        index[section_num] = text.strip()
        logger.info(
            "  Section %s: %d chars extracted",
            section_num,
            len(index[section_num]),
        )
    return index


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pbrer-slicer",
        description="Extract specific page ranges from a PBRER PDF into a section index JSON",
    )
    parser.add_argument(
        "--pbrer", required=True,
        help="Path to PBRER PDF file",
    )
    parser.add_argument(
        "--pages", required=True,
        help='Page specifications: "section:start-end, ..." (e.g. "5:1-20, 5.1:21-45")',
    )
    parser.add_argument(
        "--output", default="data/template/pbrer_index.json",
        help="Output JSON file path (default: data/template/pbrer_index.json)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    pdf_path = Path(args.pbrer)
    if not pdf_path.exists():
        logger.error("PBRER PDF not found: %s", pdf_path)
        sys.exit(1)

    # Show total page count for reference
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    doc.close()
    logger.info("PBRER has %d total pages", total_pages)

    page_specs = parse_page_spec(args.pages)
    if not page_specs:
        logger.error("No valid page specifications found in: %s", args.pages)
        sys.exit(1)

    logger.info("Extracting %d sections from PBRER", len(page_specs))
    index = build_pbrer_index_from_pages(pdf_path, page_specs)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("PBRER index written to %s (%d sections)", output_path, len(index))

    # Print summary
    print(f"\nPBRER index saved to: {output_path}")
    print(f"Sections extracted: {len(index)}")
    for section_num in sorted(index.keys(), key=lambda x: [int(p) for p in x.split(".")]):
        chars = len(index[section_num])
        print(f"  {section_num}: {chars:,} chars")
    print(f"\nUse with the main pipeline: --pbrer-index \"{output_path}\"")


if __name__ == "__main__":
    main()
