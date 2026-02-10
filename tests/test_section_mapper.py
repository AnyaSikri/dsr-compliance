"""Tests for enhanced section mapper (4-pass strategy)."""

from __future__ import annotations

from src.models import DSRSection, MappingTableEntry, SectionMapping, TemplateSection
from src.section_mapper import _pass_mapping_table


class TestPassMappingTable:
    def test_explicit_mapping(self) -> None:
        dsr = [
            DSRSection(section_num="1.2.1", title="Drug Background", content="content"),
        ]
        tmpl = [
            TemplateSection(section_id="1.2.1", title="Drug Background"),
        ]
        entries = [
            MappingTableEntry(
                dsr_section_id="1.2.1",
                dsr_title="Drug Background",
                source_refs=["IB 2.3"],
            ),
        ]
        mappings: dict[str, SectionMapping] = {}
        _pass_mapping_table(dsr, tmpl, entries, mappings)
        assert "1.2.1" in mappings
        assert mappings["1.2.1"].match_method == "mapping_table"
        assert mappings["1.2.1"].confidence == 1.0
        assert "IB 2.3" in mappings["1.2.1"].notes

    def test_no_match_when_template_missing(self) -> None:
        dsr = [
            DSRSection(section_num="9.9", title="Unknown", content="content"),
        ]
        tmpl = [
            TemplateSection(section_id="1.1", title="Intro"),
        ]
        entries = [
            MappingTableEntry(dsr_section_id="9.9", source_refs=["IB 1.0"]),
        ]
        mappings: dict[str, SectionMapping] = {}
        _pass_mapping_table(dsr, tmpl, entries, mappings)
        # 9.9 is not in template_sections, so no mapping created
        assert "9.9" not in mappings

    def test_already_mapped_skipped(self) -> None:
        dsr = [
            DSRSection(section_num="1.1", title="Intro", content="content"),
        ]
        tmpl = [
            TemplateSection(section_id="1.1", title="Intro"),
        ]
        entries = [
            MappingTableEntry(dsr_section_id="1.1", source_refs=["IB 1.0"]),
        ]
        # Pre-populate with existing mapping
        mappings: dict[str, SectionMapping] = {
            "1.1": SectionMapping(
                dsr_section="1.1",
                dsr_title="Intro",
                match_method="exact_title",
            ),
        }
        _pass_mapping_table(dsr, tmpl, entries, mappings)
        # Should keep original mapping, not overwrite
        assert mappings["1.1"].match_method == "exact_title"

    def test_multiple_entries(self) -> None:
        dsr = [
            DSRSection(section_num="1.2.1", title="Drug Background", content="c1"),
            DSRSection(section_num="1.2.1.1", title="Therapeutic Indications", content="c2"),
        ]
        tmpl = [
            TemplateSection(section_id="1.2.1", title="Drug Background"),
            TemplateSection(section_id="1.2.1.1", title="Therapeutic Indications"),
        ]
        entries = [
            MappingTableEntry(dsr_section_id="1.2.1", source_refs=["IB 2.3"]),
            MappingTableEntry(dsr_section_id="1.2.1.1", source_refs=["IB 6.1", "PBRER 1.3"]),
        ]
        mappings: dict[str, SectionMapping] = {}
        _pass_mapping_table(dsr, tmpl, entries, mappings)
        assert len(mappings) == 2
        assert mappings["1.2.1"].match_method == "mapping_table"
        assert mappings["1.2.1.1"].match_method == "mapping_table"

    def test_empty_entries(self) -> None:
        dsr = [DSRSection(section_num="1.1", title="Intro", content="c")]
        tmpl = [TemplateSection(section_id="1.1", title="Intro")]
        mappings: dict[str, SectionMapping] = {}
        _pass_mapping_table(dsr, tmpl, [], mappings)
        assert len(mappings) == 0
