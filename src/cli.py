"""CLI entry point with two subcommands: from-pdf and from-sections.

Usage:
    python -m src.cli from-pdf --pdf DSR.pdf --template template.txt --scope "1.1-1.2.2.4"
    python -m src.cli from-sections --sections-dir ./sections/ --index-csv index.csv \
        --template template.txt --scope "1.1-1.2.2.4"
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from .config import Config
from .deliverables import generate_all_deliverables
from .literature_resolver import load_literature_index
from .models import DSRSection
from .openai_client import LLMClient
from .section_mapper import map_sections
from .template_parser import get_mapping_entries, parse_template, read_template_text
from .utils import logger, setup_logging
from .validators import run_all


def _load_dsr_sections_from_csv(
    index_csv: Path,
    sections_dir: Path,
) -> list[DSRSection]:
    """Load DSR sections from an index CSV + .md files on disk."""
    sections: list[DSRSection] = []
    with open(index_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            section_num = row.get("section_num", "").strip()
            title = row.get("title", "").strip()
            heading_full = row.get("heading_full", "").strip()
            page_start = int(row.get("page_start", 0))
            page_end = int(row.get("page_end", 0))
            file_field = row.get("file", "").strip()

            # Resolve the .md filename
            filename = Path(file_field).name
            md_path = sections_dir / filename
            if not md_path.exists():
                # Try nested directory
                md_path = sections_dir / "dsr_sections" / filename
            content = ""
            if md_path.exists():
                content = md_path.read_text(encoding="utf-8")

            sections.append(DSRSection(
                section_num=section_num,
                title=title,
                heading_full=heading_full,
                page_start=page_start,
                page_end=page_end,
                file=filename,
                content=content,
            ))
    return sections


def cmd_from_sections(args: argparse.Namespace) -> int:
    """Execute the from-sections pipeline."""
    config = Config.from_env(
        model=args.model,
        template_path=Path(args.template),
        ib_path=Path(args.ib),
        sections_dir=Path(args.sections_dir),
        index_csv=Path(args.index_csv),
        output_dir=Path(args.output_dir),
        intermediate_dir=Path(args.output_dir).parent / "intermediate",
        traced_output_dir=Path(args.output_dir).parent / "output",
        scope=args.scope,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )
    errors = config.validate()
    if not Path(args.ib).exists():
        errors.append(f"IB PDF file not found: {args.ib}")
    if errors:
        for e in errors:
            logger.error(e)
        return 1

    llm = LLMClient(config)

    # Step 1: Parse template
    logger.info("Step 1: Parsing template")
    template_sections = parse_template(config.template_path, config, llm)

    # Step 1b: Get mapping table entries from template
    mapping_entries = get_mapping_entries(config.template_path)
    if mapping_entries:
        logger.info("Loaded %d mapping table entries from template", len(mapping_entries))

    # Step 2: Load DSR sections
    logger.info("Step 2: Loading DSR sections from index CSV")
    dsr_sections = _load_dsr_sections_from_csv(
        config.index_csv, config.sections_dir,
    )
    logger.info("Loaded %d DSR sections", len(dsr_sections))

    # Step 2b: Build PBRER index if provided
    pbrer_index = _load_pbrer_index(args)

    # Step 2c: Load literature index if provided
    literature_results: dict[str, str] | None = None
    if getattr(args, "literature", None):
        logger.info("Loading literature index from %s", args.literature)
        literature_results = load_literature_index(Path(args.literature))
        logger.info("Literature index: %d entries", len(literature_results))

    # Step 2d: Build vector store if enabled
    vector_store = None
    if not getattr(args, "no_vectors", False) and not config.dry_run:
        try:
            from .vector_store import VectorStore

            vector_store = VectorStore(config, openai_client=llm.client)
            # Index template sections
            tmpl_texts = [f"{s.section_id} {s.title} {s.body or ''}" for s in template_sections]
            tmpl_meta = [{"section_id": s.section_id, "title": s.title} for s in template_sections]
            vector_store.add_documents(tmpl_texts, tmpl_meta, source_type="template")
            logger.info("Vector store: indexed %d template sections", len(tmpl_texts))
        except ImportError:
            logger.warning("Vector store dependencies not available — skipping vectorization")

    # Step 3: Map sections
    logger.info("Step 3: Mapping DSR sections to template")
    mappings = map_sections(
        dsr_sections, template_sections, llm,
        mapping_entries=mapping_entries or None,
        vector_store=vector_store,
    )

    # Step 4: Generate deliverables
    logger.info("Step 4: Generating deliverables")
    paths = generate_all_deliverables(
        template_sections, mappings, config, args.scope, config.sections_dir,
    )

    # Step 4b: Populate filled template from IB (with LLM synthesis)
    logger.info("Step 4b: Populating filled template from IB")
    from .ib_extractor import build_ib_index
    from .template_populator import write_filled_template

    ib_index = build_ib_index(Path(args.ib))
    filled_paths = write_filled_template(
        template_sections, ib_index, config.traced_output_dir,
        llm=llm,
        dry_run=config.dry_run,
        pbrer_index=pbrer_index,
        literature_results=literature_results,
    )
    logger.info("Filled template: %s, %s", filled_paths["md"], filled_paths["docx"])

    # Step 5: Validate
    logger.info("Step 5: Running validation")
    template_text = read_template_text(config.template_path)
    vresult = run_all(
        template_text=template_text,
        source_rules_path=paths["source_rules"],
        mapping_path=paths["mapping"],
        snapshot_path=paths["snapshot"],
        traced_dir=config.traced_output_dir,
        scope_str=args.scope,
        sections_dir=config.sections_dir,
    )
    print(vresult.summary())

    if vresult.all_passed:
        logger.info("All validation checks passed.")
        return 0
    else:
        logger.warning("Some validation checks failed. Review output above.")
        return 2


def cmd_from_pdf(args: argparse.Namespace) -> int:
    """Execute the from-pdf pipeline."""
    from .pdf_extractor import extract_pdf

    config = Config.from_env(
        model=args.model,
        template_path=Path(args.template),
        ib_path=Path(args.ib),
        pdf_path=Path(args.pdf),
        output_dir=Path(args.output_dir),
        intermediate_dir=Path(args.output_dir).parent / "intermediate",
        traced_output_dir=Path(args.output_dir).parent / "output",
        scope=args.scope,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )
    errors = config.validate()
    if not config.pdf_path.exists():
        errors.append(f"PDF file not found: {config.pdf_path}")
    if not Path(args.ib).exists():
        errors.append(f"IB PDF file not found: {args.ib}")
    if errors:
        for e in errors:
            logger.error(e)
        return 1

    llm = LLMClient(config)

    # Step 1: Extract sections from PDF
    logger.info("Step 1: Extracting sections from PDF")
    dsr_sections, index_csv = extract_pdf(config.pdf_path, config, llm)
    logger.info("Extracted %d sections", len(dsr_sections))

    # Step 2: Parse template
    logger.info("Step 2: Parsing template")
    template_sections = parse_template(config.template_path, config, llm)

    # Step 2b: Get mapping table entries from template
    mapping_entries = get_mapping_entries(config.template_path)
    if mapping_entries:
        logger.info("Loaded %d mapping table entries from template", len(mapping_entries))

    # Step 2c: Build PBRER index if provided
    pbrer_index = _load_pbrer_index(args)

    # Step 2d: Load literature index if provided
    literature_results: dict[str, str] | None = None
    if getattr(args, "literature", None):
        logger.info("Loading literature index from %s", args.literature)
        literature_results = load_literature_index(Path(args.literature))
        logger.info("Literature index: %d entries", len(literature_results))

    # Step 2e: Build vector store if enabled
    vector_store = None
    if not getattr(args, "no_vectors", False) and not config.dry_run:
        try:
            from .vector_store import VectorStore

            vector_store = VectorStore(config, openai_client=llm.client)
            # Index template sections
            tmpl_texts = [f"{s.section_id} {s.title} {s.body or ''}" for s in template_sections]
            tmpl_meta = [{"section_id": s.section_id, "title": s.title} for s in template_sections]
            vector_store.add_documents(tmpl_texts, tmpl_meta, source_type="template")
            logger.info("Vector store: indexed %d template sections", len(tmpl_texts))
        except ImportError:
            logger.warning("Vector store dependencies not available — skipping vectorization")

    # Step 3: Map sections
    logger.info("Step 3: Mapping DSR sections to template")
    mappings = map_sections(
        dsr_sections, template_sections, llm,
        mapping_entries=mapping_entries or None,
        vector_store=vector_store,
    )

    # Step 4: Generate deliverables
    logger.info("Step 4: Generating deliverables")
    sections_dir = config.intermediate_dir / "dsr_sections"
    paths = generate_all_deliverables(
        template_sections, mappings, config, args.scope, sections_dir,
    )

    # Step 4b: Populate filled template from IB (with LLM synthesis)
    logger.info("Step 4b: Populating filled template from IB")
    from .ib_extractor import build_ib_index
    from .template_populator import write_filled_template

    ib_index = build_ib_index(Path(args.ib))
    filled_paths = write_filled_template(
        template_sections, ib_index, config.traced_output_dir,
        llm=llm,
        dry_run=config.dry_run,
        pbrer_index=pbrer_index,
        literature_results=literature_results,
    )
    logger.info("Filled template: %s, %s", filled_paths["md"], filled_paths["docx"])

    # Step 5: Validate
    logger.info("Step 5: Running validation")
    template_text = read_template_text(config.template_path)
    vresult = run_all(
        template_text=template_text,
        source_rules_path=paths["source_rules"],
        mapping_path=paths["mapping"],
        snapshot_path=paths["snapshot"],
        traced_dir=config.traced_output_dir,
        scope_str=args.scope,
        sections_dir=sections_dir,
    )
    print(vresult.summary())

    if vresult.all_passed:
        logger.info("All validation checks passed.")
        return 0
    else:
        logger.warning("Some validation checks failed. Review output above.")
        return 2


def _load_pbrer_index(args: argparse.Namespace) -> dict[str, str] | None:
    """Load PBRER index from --pbrer-index JSON or --pbrer PDF."""
    if getattr(args, "pbrer_index", None):
        import json
        path = Path(args.pbrer_index)
        logger.info("Loading pre-built PBRER index from %s", path)
        index = json.loads(path.read_text(encoding="utf-8"))
        logger.info("PBRER index: %d sections", len(index))
        return index

    if getattr(args, "pbrer", None):
        from .pbrer_extractor import build_pbrer_index
        logger.info("Building PBRER index from %s", args.pbrer)
        index = build_pbrer_index(Path(args.pbrer))
        logger.info("PBRER index: %d sections", len(index))
        return index

    return None


def _add_common_enhancement_args(parser: argparse.ArgumentParser) -> None:
    """Add --pbrer, --pbrer-index, --literature, --no-vectors to a subparser."""
    parser.add_argument(
        "--pbrer", default=None,
        help="Path to PBRER PDF for auto-extraction (all pages)",
    )
    parser.add_argument(
        "--pbrer-index", default=None,
        help="Path to pre-built PBRER index JSON (from pbrer_slicer)",
    )
    parser.add_argument(
        "--literature", default=None,
        help="Path to literature index JSON (keyword → content)",
    )
    parser.add_argument(
        "--no-vectors", action="store_true",
        help="Disable vector similarity matching (use keyword fallback only)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dsr-compliance",
        description="Generate compliance deliverables from regulatory templates + DSR",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- from-sections subcommand ---
    sp_sections = subparsers.add_parser(
        "from-sections",
        help="Use pre-split .md section files + index CSV",
    )
    sp_sections.add_argument(
        "--sections-dir", required=True,
        help="Directory containing .md section files",
    )
    sp_sections.add_argument(
        "--index-csv", required=True,
        help="Path to dsr_sections_index.csv",
    )
    sp_sections.add_argument(
        "--template", required=True,
        help="Path to regulatory template (.txt or .docx)",
    )
    sp_sections.add_argument(
        "--ib", required=True,
        help="Path to Investigator's Brochure PDF",
    )
    sp_sections.add_argument(
        "--scope", required=True,
        help="Section scope range, e.g. '1.1-1.2.2.4'",
    )
    sp_sections.add_argument(
        "--model", default="gpt-4o",
        help="OpenAI model to use (default: gpt-4o)",
    )
    sp_sections.add_argument(
        "--output-dir", default="data/mappings",
        help="Directory for deliverable output files",
    )
    sp_sections.add_argument(
        "--dry-run", action="store_true",
        help="Skip actual API calls (use placeholder responses)",
    )
    sp_sections.add_argument(
        "--verbose", action="store_true",
        help="Enable debug logging",
    )
    _add_common_enhancement_args(sp_sections)
    sp_sections.set_defaults(func=cmd_from_sections)

    # --- from-pdf subcommand ---
    sp_pdf = subparsers.add_parser(
        "from-pdf",
        help="Extract sections from a DSR PDF",
    )
    sp_pdf.add_argument(
        "--pdf", required=True,
        help="Path to DSR PDF file",
    )
    sp_pdf.add_argument(
        "--template", required=True,
        help="Path to regulatory template (.txt or .docx)",
    )
    sp_pdf.add_argument(
        "--ib", required=True,
        help="Path to Investigator's Brochure PDF",
    )
    sp_pdf.add_argument(
        "--scope", required=True,
        help="Section scope range, e.g. '1.1-1.2.2.4'",
    )
    sp_pdf.add_argument(
        "--model", default="gpt-4o",
        help="OpenAI model to use (default: gpt-4o)",
    )
    sp_pdf.add_argument(
        "--output-dir", default="data/mappings",
        help="Directory for deliverable output files",
    )
    sp_pdf.add_argument(
        "--dry-run", action="store_true",
        help="Skip actual API calls (use placeholder responses)",
    )
    sp_pdf.add_argument(
        "--verbose", action="store_true",
        help="Enable debug logging",
    )
    _add_common_enhancement_args(sp_pdf)
    sp_pdf.set_defaults(func=cmd_from_pdf)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(args.verbose)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
