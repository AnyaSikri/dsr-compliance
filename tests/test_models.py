"""Tests for Pydantic model extensions."""

from __future__ import annotations

from src.models import MappingTableEntry, SectionMapping, TemplateSection


class TestTemplateSectionExtensions:
    def test_mapping_table_sources_default_empty(self) -> None:
        ts = TemplateSection(section_id="1.1", title="Intro")
        assert ts.mapping_table_sources == {}

    def test_ignore_default_false(self) -> None:
        ts = TemplateSection(section_id="1.1", title="Intro")
        assert ts.ignore is False

    def test_mapping_table_sources_set(self) -> None:
        ts = TemplateSection(
            section_id="1.2.1",
            title="Drug Background",
            mapping_table_sources={"ib": ["IB 2.3"], "pbrer": ["PBRER 1.3"]},
        )
        assert ts.mapping_table_sources["ib"] == ["IB 2.3"]
        assert ts.mapping_table_sources["pbrer"] == ["PBRER 1.3"]

    def test_ignore_set_true(self) -> None:
        ts = TemplateSection(section_id="99", title="IGNORE", ignore=True)
        assert ts.ignore is True


class TestMappingTableEntry:
    def test_basic_construction(self) -> None:
        entry = MappingTableEntry(
            dsr_section_id="1.2.1",
            dsr_title="Drug Background",
            source_refs=["IB 2.3", "PBRER 1.3"],
        )
        assert entry.dsr_section_id == "1.2.1"
        assert entry.dsr_title == "Drug Background"
        assert len(entry.source_refs) == 2

    def test_default_empty_fields(self) -> None:
        entry = MappingTableEntry(dsr_section_id="1.1")
        assert entry.dsr_title == ""
        assert entry.source_refs == []


class TestSectionMappingConfidence:
    def test_confidence_default_zero(self) -> None:
        sm = SectionMapping(dsr_section="1.1", dsr_title="Intro")
        assert sm.confidence == 0.0

    def test_confidence_set(self) -> None:
        sm = SectionMapping(
            dsr_section="1.1",
            dsr_title="Intro",
            confidence=0.95,
        )
        assert sm.confidence == 0.95
