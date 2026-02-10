"""Generate all 4 compliance deliverables per SOP-SAF-001.

1. template_source_rules.yaml
2. template_to_dsr_map.yaml
3. SOURCE TRACE blocks in .md copies
4. compliance_snapshot.csv
"""

from __future__ import annotations

import csv
import io
import shutil
from pathlib import Path

import yaml

from .config import Config
from .models import (
    ComplianceRow,
    SectionMapping,
    SourceTraceBlock,
    TemplateSection,
)
from .utils import ensure_dir, logger, parse_scope, section_in_scope


# --------------------------------------------------------------------------
# 1. template_source_rules.yaml
# --------------------------------------------------------------------------

def generate_source_rules(
    template_sections: list[TemplateSection],
    output_dir: Path,
) -> Path:
    """Write template_source_rules.yaml."""
    entries = []
    for s in template_sections:
        entry: dict = {
            "section_id": s.section_id,
            "title": s.title,
            "required_sources": s.required_sources,
        }
        if s.notes:
            entry["notes"] = s.notes
        entries.append(entry)

    data = {"template_sections": entries}
    header = (
        "# Template Source Rules\n"
        "# Each entry captures ONLY what the template explicitly states as required sources.\n"
        "# No sources have been inferred from pharma conventions.\n\n"
    )
    out_path = ensure_dir(output_dir) / "template_source_rules.yaml"
    content = header + yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
    out_path.write_text(content, encoding="utf-8")
    logger.info("Written: %s", out_path)
    return out_path


# --------------------------------------------------------------------------
# 2. template_to_dsr_map.yaml
# --------------------------------------------------------------------------

def generate_mapping_file(
    mappings: list[SectionMapping],
    scope_str: str,
    output_dir: Path,
) -> Path:
    """Write template_to_dsr_map.yaml with in-scope mappings and future_mappings."""
    scope = parse_scope(scope_str)
    in_scope: list[dict] = []
    future: list[dict] = []

    for m in mappings:
        entry: dict = {
            "dsr_section": m.dsr_section,
            "dsr_title": m.dsr_title,
            "dsr_file": m.dsr_file,
            "template_section": m.template_section,
            "template_title": m.template_title,
            "match_method": m.match_method,
        }
        if m.notes:
            entry["notes"] = m.notes

        if section_in_scope(m.dsr_section, scope):
            in_scope.append(entry)
        else:
            # Future mappings don't need dsr_file
            future_entry = {k: v for k, v in entry.items() if k != "dsr_file"}
            future.append(future_entry)

    header = (
        "# Template-to-DSR Section Mapping\n"
        f"# Scope for SOURCE TRACE and compliance: DSR sections {scope_str}\n"
        "# Full template coverage included below for future extension.\n\n"
        "# --- IN SCOPE ---\n\n"
    )

    data: dict = {"mappings": in_scope}
    if future:
        data["future_mappings"] = future

    out_path = ensure_dir(output_dir) / "template_to_dsr_map.yaml"
    content = header + yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
    out_path.write_text(content, encoding="utf-8")
    logger.info("Written: %s", out_path)
    return out_path


# --------------------------------------------------------------------------
# 3. SOURCE TRACE blocks
# --------------------------------------------------------------------------

def _build_trace_block(
    mapping: SectionMapping,
    template_sections: list[TemplateSection],
) -> str:
    """Build a SOURCE TRACE block for one mapping."""
    if mapping.template_section is None:
        block = SourceTraceBlock()
        return block.render()

    # Find the template section to get its required_sources
    tmpl = next(
        (t for t in template_sections if t.section_id == mapping.template_section),
        None,
    )
    sources = tmpl.required_sources if tmpl else []
    block = SourceTraceBlock(
        template_section_id=mapping.template_section,
        template_section_title=mapping.template_title or "",
        required_sources=sources,
    )
    return block.render()


def generate_traced_files(
    mappings: list[SectionMapping],
    template_sections: list[TemplateSection],
    sections_dir: Path,
    output_dir: Path,
    scope_str: str,
) -> list[Path]:
    """Copy in-scope .md files to output_dir with SOURCE TRACE blocks prepended.

    Original files are NEVER modified in place.
    """
    scope = parse_scope(scope_str)
    out = ensure_dir(output_dir)
    written: list[Path] = []

    for m in mappings:
        if not section_in_scope(m.dsr_section, scope):
            continue

        # Find the source .md file
        src_file = _find_md_file(m.dsr_file, sections_dir)
        if src_file is None:
            logger.warning("Source file not found for DSR %s: %s", m.dsr_section, m.dsr_file)
            continue

        trace = _build_trace_block(m, template_sections)
        original_content = src_file.read_text(encoding="utf-8")

        # Strip any existing SOURCE TRACE block from the content
        stripped = _strip_existing_trace(original_content)

        new_content = trace + "\n\n" + stripped
        dest = out / src_file.name
        dest.write_text(new_content, encoding="utf-8")
        written.append(dest)
        logger.debug("Traced: %s", dest.name)

    logger.info("Written %d traced .md files to %s", len(written), out)
    return written


def _find_md_file(dsr_file: str, sections_dir: Path) -> Path | None:
    """Locate the .md file, handling both relative names and full paths."""
    # Try the filename directly under sections_dir
    name = Path(dsr_file).name
    candidate = sections_dir / name
    if candidate.exists():
        return candidate
    # Try as-is
    p = Path(dsr_file)
    if p.exists():
        return p
    # Try looking in a nested dsr_sections subdir
    nested = sections_dir / "dsr_sections" / name
    if nested.exists():
        return nested
    return None


def _strip_existing_trace(content: str) -> str:
    """Remove any existing <!-- SOURCE TRACE ... --> block from content."""
    import re
    return re.sub(
        r"<!--\s*SOURCE\s+TRACE\s*\n.*?-->\s*\n*",
        "",
        content,
        flags=re.DOTALL,
    ).lstrip("\n")


# --------------------------------------------------------------------------
# 4. compliance_snapshot.csv
# --------------------------------------------------------------------------

def generate_compliance_snapshot(
    mappings: list[SectionMapping],
    template_sections: list[TemplateSection],
    scope_str: str,
    output_dir: Path,
) -> Path:
    """Write compliance_snapshot.csv with one row per in-scope section."""
    scope = parse_scope(scope_str)
    rows: list[ComplianceRow] = []

    for m in mappings:
        if not section_in_scope(m.dsr_section, scope):
            continue

        if m.template_section is None:
            row = ComplianceRow(
                dsr_section=m.dsr_section,
                dsr_title=m.dsr_title,
                template_section="",
                template_title="",
                required_sources="N/A",
                status="NOT MAPPED",
                notes=m.notes or "No template analog identified",
            )
        else:
            tmpl = next(
                (t for t in template_sections if t.section_id == m.template_section),
                None,
            )
            sources_str = ", ".join(tmpl.required_sources) if tmpl and tmpl.required_sources else ""
            row = ComplianceRow(
                dsr_section=m.dsr_section,
                dsr_title=m.dsr_title,
                template_section=m.template_section,
                template_title=m.template_title or "",
                required_sources=sources_str,
                status="NOT VERIFIED",
                notes=m.notes if "parent" in m.notes.lower() or "subsection" in m.notes.lower() else "",
            )
        rows.append(row)

    out_path = ensure_dir(output_dir) / "compliance_snapshot.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(ComplianceRow.model_fields.keys())
        for r in rows:
            writer.writerow([
                r.dsr_section,
                r.dsr_title,
                r.template_section,
                r.template_title,
                r.required_sources,
                r.status,
                r.notes,
            ])

    logger.info("Written: %s (%d rows)", out_path, len(rows))
    return out_path


# --------------------------------------------------------------------------
# Convenience: generate all 4 at once
# --------------------------------------------------------------------------

def generate_all_deliverables(
    template_sections: list[TemplateSection],
    mappings: list[SectionMapping],
    config: Config,
    scope_str: str,
    sections_dir: Path,
) -> dict[str, Path]:
    """Generate all 4 deliverables and return their paths."""
    paths: dict[str, Path] = {}

    paths["source_rules"] = generate_source_rules(
        template_sections, config.output_dir,
    )
    paths["mapping"] = generate_mapping_file(
        mappings, scope_str, config.output_dir,
    )
    paths["snapshot"] = generate_compliance_snapshot(
        mappings, template_sections, scope_str, config.output_dir,
    )
    paths["traced_files"] = generate_traced_files(
        mappings, template_sections, sections_dir, config.traced_output_dir, scope_str,
    )
    # traced_files returns a list; store the directory
    paths["traced_dir"] = config.traced_output_dir

    return paths
