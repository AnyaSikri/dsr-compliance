"""End-to-end tests for enhanced pipeline components.

These tests verify that the full data flow works correctly when all
new components are wired together: mapping table entries, multi-source
resolution, and the template populator with PBRER + literature.
"""

from __future__ import annotations

from src.ib_resolver import resolve_sources
from src.models import (
    DSRSection,
    MappingTableEntry,
    SectionMapping,
    TemplateSection,
)
from src.section_mapper import _pass_mapping_table
from src.template_populator import assemble_markdown


class TestMappingTableToPopulatorFlow:
    """Verify that mapping table entries flow through to the populator."""

    def test_mapping_table_match_then_resolve(self) -> None:
        """Mapping table match → resolve_sources uses correct IB section."""
        dsr = [
            DSRSection(section_num="1.2.1", title="Drug Background", content="c"),
        ]
        tmpl = [
            TemplateSection(
                section_id="1.2.1",
                title="Drug Background",
                required_sources=["IB 2.3"],
            ),
        ]
        entries = [
            MappingTableEntry(
                dsr_section_id="1.2.1",
                dsr_title="Drug Background",
                source_refs=["IB 2.3"],
            ),
        ]
        # Pass 0 mapping
        mappings: dict[str, SectionMapping] = {}
        _pass_mapping_table(dsr, tmpl, entries, mappings)
        assert "1.2.1" in mappings
        assert mappings["1.2.1"].confidence == 1.0

        # Now resolve sources for the template section
        ib_index = {"2.3": "Drug background content from IB."}
        resolved = resolve_sources(["IB 2.3"], ib_index)
        assert resolved[0].found is True
        assert resolved[0].content == "Drug background content from IB."


class TestMultiSourceAssembly:
    """Verify assemble_markdown produces correct output with all source types."""

    def test_ib_only_backward_compat(self) -> None:
        """Calling without new params produces same output as before."""
        sections = [
            TemplateSection(
                section_id="1.1",
                title="Introduction",
                required_sources=["IB 2.3"],
            ),
        ]
        ib_index = {"2.3": "IB content for 2.3."}
        md = assemble_markdown(sections, ib_index)
        assert "IB content for 2.3." in md
        assert "Source: IB 2.3" in md

    def test_pbrer_resolved_in_assembly(self) -> None:
        """PBRER source is resolved when pbrer_index is provided."""
        sections = [
            TemplateSection(
                section_id="1.2",
                title="Safety Overview",
                required_sources=["PBRER 1.3"],
            ),
        ]
        ib_index = {}
        pbrer_index = {"1.3": "PBRER safety data."}
        md = assemble_markdown(sections, ib_index, pbrer_index=pbrer_index)
        assert "PBRER safety data." in md

    def test_literature_resolved_in_assembly(self) -> None:
        """External source is resolved when literature_results is provided."""
        sections = [
            TemplateSection(
                section_id="1.3",
                title="Literature Review",
                required_sources=["UpToDate"],
            ),
        ]
        ib_index = {}
        literature_results = {"UpToDate": "Clinical review from UpToDate."}
        md = assemble_markdown(
            sections, ib_index, literature_results=literature_results,
        )
        assert "Clinical review from UpToDate." in md

    def test_mixed_sources_all_resolved(self) -> None:
        """All three source types resolved in a single section."""
        sections = [
            TemplateSection(
                section_id="1.4",
                title="Combined Assessment",
                required_sources=["IB 2.3", "PBRER 1.3", "UpToDate"],
            ),
        ]
        ib_index = {"2.3": "IB data."}
        pbrer_index = {"1.3": "PBRER data."}
        literature_results = {"UpToDate": "Literature data."}
        md = assemble_markdown(
            sections, ib_index,
            pbrer_index=pbrer_index,
            literature_results=literature_results,
        )
        assert "IB data." in md
        assert "PBRER data." in md
        assert "Literature data." in md
        # Multiple sources -> subheadings
        assert "### From IB 2.3" in md
        assert "### From PBRER 1.3" in md
        assert "### From UpToDate" in md

    def test_unresolved_pbrer_produces_placeholder(self) -> None:
        """PBRER without index produces manual input placeholder."""
        sections = [
            TemplateSection(
                section_id="1.5",
                title="PBRER Section",
                required_sources=["PBRER 9.9"],
            ),
        ]
        ib_index = {}
        md = assemble_markdown(sections, ib_index)
        assert "ADDITIONAL DATA NEEDED" in md

    def test_ignore_section_excluded(self) -> None:
        """Sections marked ignore should not appear in output when filtered before assembly."""
        sections = [
            TemplateSection(section_id="1.1", title="Active", required_sources=["IB 2.3"]),
            TemplateSection(section_id="2.1", title="Old Version", ignore=True),
        ]
        # Filter out ignore sections (as parse_template does)
        active = [s for s in sections if not s.ignore]
        ib_index = {"2.3": "IB content."}
        md = assemble_markdown(active, ib_index)
        assert "Active" in md
        assert "Old Version" not in md


class TestBackwardCompatibility:
    """Verify that calling enhanced functions without new params works identically."""

    def test_resolve_sources_no_extra_params(self) -> None:
        """resolve_sources with only ib_index works as before."""
        ib_index = {"2.3": "content"}
        result = resolve_sources(["IB 2.3", "PBRER 1.3", "UpToDate"], ib_index)
        assert result[0].found is True
        assert result[1].found is False
        assert "ADDITIONAL DATA NEEDED" in result[1].content
        assert result[2].found is False
        assert "ADDITIONAL DATA NEEDED" in result[2].content

    def test_assemble_markdown_no_extra_params(self) -> None:
        """assemble_markdown with only ib_index works as before."""
        sections = [
            TemplateSection(section_id="1.1", title="Intro", body="Intro body."),
        ]
        md = assemble_markdown(sections, {})
        assert "Intro" in md
        assert "Intro body." in md

    def test_mapping_table_pass_empty_entries(self) -> None:
        """map_sections with no mapping_entries param uses 3-pass behavior."""
        dsr = [DSRSection(section_num="1.1", title="Intro", content="c")]
        tmpl = [TemplateSection(section_id="1.1", title="Intro")]
        mappings: dict[str, SectionMapping] = {}
        _pass_mapping_table(dsr, tmpl, [], mappings)
        assert len(mappings) == 0
