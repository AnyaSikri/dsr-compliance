"""Tests for template_populator module."""

from __future__ import annotations

import pytest

from src.models import TemplateSection
from src.template_populator import assemble_markdown


class TestAssembleMarkdown:
    def setup_method(self):
        self.ib_index = {
            "2.3": "Pralsetinib is a kinase inhibitor targeting RET.",
            "1.2": "Available as 100mg capsules.",
            "3.2": "Detailed formulation: excipients include...",
            "6.1": "Approved for RET-positive NSCLC.",
        }

    def test_single_ib_ref_populated(self):
        # Section with one IB ref -> content inserted with Source label
        sections = [TemplateSection(section_id="2.1.2", title="Therapeutic Indications", body="", required_sources=["IB 6.1"])]
        md = assemble_markdown(sections, self.ib_index)
        assert "## 2.1.2 Therapeutic Indications" in md
        assert "Approved for RET-positive NSCLC." in md
        assert "IB 6.1" in md

    def test_multiple_ib_refs_get_subheadings(self):
        # Section with 3 IB refs -> each gets a subheading
        sections = [TemplateSection(section_id="2.1.1", title="Drug Pharmacology", body="", required_sources=["IB 2.3", "IB 1.2", "IB 3.2"])]
        md = assemble_markdown(sections, self.ib_index)
        assert "### From IB 2.3" in md
        assert "### From IB 1.2" in md
        assert "### From IB 3.2" in md
        assert "Pralsetinib is a kinase inhibitor" in md
        assert "100mg capsules" in md

    def test_non_ib_ref_gets_placeholder(self):
        sections = [TemplateSection(section_id="2.1.3", title="Patient exposure", body="", required_sources=["PBRER Section 5"])]
        md = assemble_markdown(sections, self.ib_index)
        assert "[MANUAL INPUT REQUIRED: PBRER Section 5]" in md

    def test_no_sources_keeps_body(self):
        sections = [TemplateSection(section_id="4", title="Discussion", body="Discuss findings here.", required_sources=[])]
        md = assemble_markdown(sections, self.ib_index)
        assert "## 4 Discussion" in md
        assert "Discuss findings here." in md

    def test_ib_ref_not_found(self):
        sections = [TemplateSection(section_id="3.1", title="Review of toxicology data", body="", required_sources=["IB Section 4.3.3"])]
        md = assemble_markdown(sections, self.ib_index)
        assert "[CONTENT NOT FOUND: IB Section 4.3.3]" in md

    def test_bare_ib_gets_placeholder(self):
        sections = [TemplateSection(section_id="2.1", title="Product Background", body="", required_sources=["IB"])]
        md = assemble_markdown(sections, self.ib_index)
        assert "[MANUAL INPUT REQUIRED: IB" in md

    def test_full_document_structure(self):
        # Verify ordering of sections
        sections = [
            TemplateSection(section_id="1", title="Introduction", body="Intro text.", required_sources=[]),
            TemplateSection(section_id="2", title="Background", body="", required_sources=[]),
            TemplateSection(section_id="2.1.1", title="Drug Pharmacology", body="", required_sources=["IB 2.3"]),
        ]
        md = assemble_markdown(sections, self.ib_index)
        intro_pos = md.index("Introduction")
        bg_pos = md.index("Background")
        pharm_pos = md.index("Drug Pharmacology")
        assert intro_pos < bg_pos < pharm_pos
