"""Pydantic models for all data structures used across the pipeline."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TemplateSection(BaseModel):
    """A single section parsed from the regulatory template."""

    section_id: str = Field(description="Section number or identifier (e.g. '2.1.1')")
    title: str = Field(description="Section title")
    body: str = Field(default="", description="Full section body text")
    required_sources: list[str] = Field(
        default_factory=list,
        description="Verbatim-extracted source references",
    )
    notes: str = Field(default="", description="Factual notes from template text")
    mapping_table_sources: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Explicit source mappings from the template's mapping table. "
        "Keys are source type (e.g. 'ib', 'pbrer'), values are section refs.",
    )
    ignore: bool = Field(
        default=False,
        description="If True, this section is excluded from processing.",
    )


class MappingTableEntry(BaseModel):
    """One row from the template's mapping table at the top of the document."""

    dsr_section_id: str = Field(description="DSR section number (e.g. '1.2.1')")
    dsr_title: str = Field(default="", description="DSR section title")
    source_refs: list[str] = Field(
        default_factory=list,
        description="Source references (e.g. ['IB 2.3', 'PBRER 1.3'])",
    )


class DSRSection(BaseModel):
    """A section from the DSR (either pre-split .md or PDF-extracted)."""

    section_num: str = Field(description="Dotted-decimal section number")
    title: str = Field(description="Section title")
    heading_full: str = Field(default="", description="Full heading line")
    page_start: int = Field(default=0)
    page_end: int = Field(default=0)
    file: str = Field(default="", description="Path to .md file")
    content: str = Field(default="", description="Full markdown content")


class SectionMapping(BaseModel):
    """A mapping between one DSR section and one template section."""

    dsr_section: str
    dsr_title: str
    dsr_file: str = ""
    template_section: str | None = None
    template_title: str | None = None
    match_method: str = "no_match"
    confidence: float = Field(default=0.0, description="Match confidence score (0.0-1.0)")
    notes: str = ""


class ComplianceRow(BaseModel):
    """One row in the compliance snapshot CSV."""

    dsr_section: str
    dsr_title: str
    template_section: str = ""
    template_title: str = ""
    required_sources: str = ""
    status: str = "NOT VERIFIED"
    notes: str = ""


class SourceTraceBlock(BaseModel):
    """Data for a SOURCE TRACE HTML comment block."""

    template_section_id: str | None = None
    template_section_title: str | None = None
    required_sources: list[str] = Field(default_factory=list)
    verification_status: str = "NOT VERIFIED"
    missing_inputs: str = "Source verification"

    def render(self) -> str:
        if self.template_section_id is None:
            return (
                "<!-- SOURCE TRACE\n"
                "Template section: NOT MAPPED\n"
                "Required sources: N/A\n"
                "Verification status: NOT MAPPED\n"
                "Missing inputs: No template analog identified\n"
                "-->"
            )
        sources_str = ", ".join(self.required_sources) if self.required_sources else ""
        section_label = f"{self.template_section_id} - {self.template_section_title}"
        return (
            "<!-- SOURCE TRACE\n"
            f"Template section: {section_label}\n"
            f"Required sources: {sources_str}\n"
            f"Verification status: {self.verification_status}\n"
            f"Missing inputs: {self.missing_inputs}\n"
            "-->"
        )
