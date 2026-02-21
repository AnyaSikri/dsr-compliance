"""Template populator: assemble a filled markdown document and .docx from parsed template sections.

Walks parsed template sections, resolves source references using ib_resolver,
synthesizes report-ready prose via LLM, and produces a single filled markdown
document plus a .docx conversion.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from docx import Document

from src.ib_resolver import resolve_sources
from src.models import TemplateSection
from src.utils import ensure_dir, logger

if TYPE_CHECKING:
    from src.openai_client import LLMClient


# ---------------------------------------------------------------------------
# LLM synthesis prompt
# ---------------------------------------------------------------------------

SYNTHESIS_SYSTEM = """\
You are a regulatory medical writer producing a Drug Safety Report (DSR). \
Given source material extracted from reference documents (Investigator's \
Brochure, PBRER, literature databases), write the content for the specified \
section of the DSR.

RULES — follow these exactly:
1. Write in formal regulatory prose suitable for a DSR submission to health \
authorities.
2. Use ONLY the information provided in the source material. Do not add \
facts, statistics, or claims that are not supported by the provided sources.
3. Preserve all specific data points exactly: numbers, percentages, dates, \
study names, MedDRA preferred terms, patient counts, p-values.
4. Format any tabular data as markdown tables.
5. Do NOT include the template instructions in your output — they are \
guidance for you, not report content.
6. Do NOT add disclaimers, meta-commentary, or notes about your writing \
process.
7. If the source material is clearly insufficient for a complete section, \
write what you can from the available data and add a single line: \
"[ADDITIONAL DATA NEEDED: brief description of what is missing]"
8. Use section-appropriate structure: bullet lists for indications, \
prose paragraphs for background/discussion, structured summaries for \
results with quantitative data.
9. Do NOT repeat the section heading — it is already added by the system.\
"""


def _build_synthesis_prompt(
    section: TemplateSection,
    source_contents: list[tuple[str, str]],
) -> str:
    """Build the user prompt for LLM synthesis.

    Args:
        section: The template section being populated.
        source_contents: List of (source_label, content) tuples from resolved sources.
    """
    parts: list[str] = []
    parts.append(f"SECTION: {section.section_id} — {section.title}")
    parts.append("")

    if section.body:
        parts.append("TEMPLATE INSTRUCTIONS (for your guidance, do NOT include these in the output):")
        parts.append(section.body)
        parts.append("")

    if source_contents:
        parts.append("SOURCE MATERIAL:")
        for label, content in source_contents:
            parts.append(f"\n--- {label} ---")
            # Truncate very long sources to stay within token limits
            if len(content) > 12000:
                parts.append(content[:12000])
                parts.append("[... content truncated for length ...]")
            else:
                parts.append(content)
        parts.append("")
    else:
        parts.append("SOURCE MATERIAL: None available.")
        parts.append(
            "Write a structured placeholder noting what data this section "
            "requires and from which sources, based on the template instructions above."
        )

    return "\n".join(parts)


def _heading_level(section_id: str) -> int:
    """Determine the markdown heading level from a section_id's depth.

    - "1" -> ## (level 2)
    - "2.1" -> ### (level 3)
    - "2.1.1" -> #### (level 4)
    - Non-numeric ids (e.g. "Executive Summary") -> ## (level 2)
    - Cap at 6
    """
    parts = section_id.strip().split(".")
    try:
        for p in parts:
            int(p)
        depth = len(parts)
        level = depth + 1
        return min(level, 6)
    except ValueError:
        return 2


def assemble_markdown(
    template_sections: list[TemplateSection],
    ib_index: dict[str, str],
    llm: LLMClient | None = None,
    dry_run: bool = False,
    pbrer_index: dict[str, str] | None = None,
    literature_results: dict[str, str] | None = None,
) -> str:
    """Build a single markdown document from template sections and resolved content.

    When *llm* is provided and *dry_run* is False, each section's resolved
    source material is sent through the LLM for synthesis into report-ready
    prose.  In dry-run mode or when no LLM is available, the legacy behavior
    (raw source paste / template body) is preserved.
    """
    lines: list[str] = ["# Filled Signal Assessment Report\n"]
    use_synthesis = llm is not None and not dry_run

    for section in template_sections:
        level = _heading_level(section.section_id)
        hashes = "#" * level
        lines.append(f"{hashes} {section.section_id} {section.title}\n")

        if not section.required_sources:
            # No sources referenced in template
            if use_synthesis and section.body:
                # Synthesize even for sections without explicit sources —
                # the LLM can produce a structured placeholder from the
                # template instructions.
                prompt = _build_synthesis_prompt(section, [])
                try:
                    content = llm.call(
                        system_prompt=SYNTHESIS_SYSTEM,
                        user_prompt=prompt,
                        json_mode=False,
                        label=f"synth_{section.section_id}",
                    )
                    lines.append(f"{content.strip()}\n")
                except Exception as e:
                    logger.warning(
                        "Synthesis failed for %s: %s — falling back to template body",
                        section.section_id, e,
                    )
                    lines.append(f"{section.body}\n")
            elif section.body:
                lines.append(f"{section.body}\n")
        else:
            # Resolve sources
            resolved = resolve_sources(
                section.required_sources,
                ib_index,
                pbrer_index=pbrer_index,
                literature_results=literature_results,
            )

            if use_synthesis:
                # Collect resolved content for synthesis
                source_contents: list[tuple[str, str]] = []
                for rs in resolved:
                    source_contents.append((rs.original_ref, rs.content))

                prompt = _build_synthesis_prompt(section, source_contents)
                try:
                    content = llm.call(
                        system_prompt=SYNTHESIS_SYSTEM,
                        user_prompt=prompt,
                        json_mode=False,
                        label=f"synth_{section.section_id}",
                    )
                    lines.append(f"{content.strip()}\n")
                except Exception as e:
                    logger.warning(
                        "Synthesis failed for %s: %s — falling back to raw sources",
                        section.section_id, e,
                    )
                    # Fall back to legacy raw paste
                    _append_raw_sources(lines, resolved)
            else:
                # Legacy behavior: paste raw source content
                _append_raw_sources(lines, resolved)

    return "\n".join(lines)


def _append_raw_sources(lines: list[str], resolved: list) -> None:
    """Append resolved sources in the legacy raw-paste format."""
    if len(resolved) == 1:
        rs = resolved[0]
        lines.append(f"*Source: {rs.original_ref}*\n")
        lines.append(f"{rs.content}\n")
    else:
        for rs in resolved:
            lines.append(f"### From {rs.original_ref}\n")
            lines.append(f"{rs.content}\n")


def _markdown_to_docx(md_content: str, output_path: Path) -> None:
    """Convert markdown text to a .docx file using python-docx.

    Conversion rules:
    - Lines starting with ``#`` -> headings (level = number of hashes)
    - Lines wrapped in single ``*`` -> italic paragraph (source labels)
    - Lines starting with ``[MANUAL INPUT REQUIRED:`` or ``[CONTENT NOT FOUND:``
      or ``[ADDITIONAL DATA NEEDED:`` -> bold paragraph
    - Everything else -> normal paragraph
    - Skip empty lines
    """
    doc = Document()

    for line in md_content.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue

        # Heading lines
        heading_match = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if heading_match:
            hashes = heading_match.group(1)
            heading_text = heading_match.group(2)
            level = len(hashes)
            doc.add_heading(heading_text, level=min(level, 9))
            continue

        # Italic lines (wrapped in single asterisks)
        italic_match = re.match(r"^\*([^*]+)\*$", stripped)
        if italic_match:
            p = doc.add_paragraph()
            run = p.add_run(italic_match.group(1))
            run.italic = True
            continue

        # Bold lines (placeholders)
        if (
            stripped.startswith("[MANUAL INPUT REQUIRED:")
            or stripped.startswith("[CONTENT NOT FOUND:")
            or stripped.startswith("[ADDITIONAL DATA NEEDED:")
        ):
            p = doc.add_paragraph()
            run = p.add_run(stripped)
            run.bold = True
            continue

        # Normal paragraph
        doc.add_paragraph(stripped)

    doc.save(str(output_path))


def write_filled_template(
    template_sections: list[TemplateSection],
    ib_index: dict[str, str],
    output_dir: str | Path,
    llm: LLMClient | None = None,
    dry_run: bool = False,
    pbrer_index: dict[str, str] | None = None,
    literature_results: dict[str, str] | None = None,
) -> dict[str, Path]:
    """Write filled_template.md and filled_template.docx, return their paths.

    When *llm* is provided, source material is synthesized into report-ready
    prose.  Pass ``dry_run=True`` to skip synthesis and use legacy raw-paste
    behavior.

    Returns:
        ``{"md": Path(...), "docx": Path(...)}``
    """
    output_dir = Path(output_dir)
    ensure_dir(output_dir)

    md_content = assemble_markdown(
        template_sections, ib_index,
        llm=llm,
        dry_run=dry_run,
        pbrer_index=pbrer_index,
        literature_results=literature_results,
    )

    md_path = output_dir / "filled_template.md"
    md_path.write_text(md_content, encoding="utf-8")
    logger.info("Wrote filled markdown template to %s", md_path)

    docx_path = output_dir / "filled_template.docx"
    _markdown_to_docx(md_content, docx_path)
    logger.info("Wrote filled DOCX template to %s", docx_path)

    return {"md": md_path, "docx": docx_path}
