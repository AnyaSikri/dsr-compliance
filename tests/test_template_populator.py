"""Tests for template_populator module."""

from __future__ import annotations

import pytest

from src.models import TemplateSection
from src.template_populator import assemble_markdown, _resolve_ib_for_exec


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
        assert "ADDITIONAL DATA NEEDED" in md
        assert "PBRER Section 5" in md

    def test_no_sources_keeps_body(self):
        sections = [TemplateSection(section_id="4", title="Discussion", body="Discuss findings here.", required_sources=[])]
        md = assemble_markdown(sections, self.ib_index)
        assert "## 4 Discussion" in md
        assert "Discuss findings here." in md

    def test_ib_ref_not_found(self):
        sections = [TemplateSection(section_id="3.1", title="Review of toxicology data", body="", required_sources=["IB Section 4.3.3"])]
        md = assemble_markdown(sections, self.ib_index)
        assert "ADDITIONAL DATA NEEDED" in md
        assert "IB Section 4.3.3" in md

    def test_bare_ib_gets_placeholder(self):
        sections = [TemplateSection(section_id="2.1", title="Product Background", body="", required_sources=["IB"])]
        md = assemble_markdown(sections, self.ib_index)
        assert "ADDITIONAL DATA NEEDED" in md

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


class TestResolveIbForExec:
    """Test the IB section resolution for Executive Summary subsections."""

    def setup_method(self):
        self.ib_index = {
            "2.3": "Pralsetinib is a kinase inhibitor targeting RET.",
            "1.2": "Available as 100mg capsules.",
            "3.2": "Dose: 400mg once daily.",
            "6.1": "Approved for RET-positive NSCLC.",
            "6.3": "Warnings: hepatotoxicity, hypertension.",
            "4.3.3": "Non-clinical toxicology data: carcinogenicity...",
            "5.5": "Clinical study BLU-667: 120 patients enrolled.",
            "1.4.3": "Safety summary: most common AEs were...",
        }

    def test_product_info_resolves_pharmacology_sections(self):
        results = _resolve_ib_for_exec(
            "Product Background",
            "Product specific information.",
            self.ib_index,
        )
        labels = [label for label, _ in results]
        assert any("2.3" in l for l in labels), f"Expected IB 2.3, got {labels}"
        assert any("1.2" in l for l in labels), f"Expected IB 1.2, got {labels}"
        assert any("6.1" in l for l in labels), f"Expected IB 6.1, got {labels}"

    def test_event_of_interest_resolves_toxicology(self):
        results = _resolve_ib_for_exec(
            "Event of Interest",
            "Description of the event.",
            self.ib_index,
        )
        labels = [label for label, _ in results]
        assert any("4.3.3" in l for l in labels), f"Expected IB 4.3.3, got {labels}"
        assert any("6.3" in l for l in labels), f"Expected IB 6.3, got {labels}"

    def test_data_sources_resolves_clinical_sections(self):
        results = _resolve_ib_for_exec(
            "Data Sources and Methodology",
            "Describe data sources and evaluation methods.",
            self.ib_index,
        )
        labels = [label for label, _ in results]
        assert any("5.5" in l for l in labels), f"Expected IB 5.5, got {labels}"
        assert any("1.4.3" in l for l in labels), f"Expected IB 1.4.3, got {labels}"

    def test_key_results_resolves_safety_sections(self):
        results = _resolve_ib_for_exec(
            "Key Results",
            "Provide key results from the report.",
            self.ib_index,
        )
        labels = [label for label, _ in results]
        assert any("5.5" in l for l in labels), f"Expected IB 5.5, got {labels}"
        assert any("6.3" in l for l in labels), f"Expected IB 6.3, got {labels}"

    def test_rationale_returns_no_ib(self):
        results = _resolve_ib_for_exec(
            "Rationale",
            "Reason for the report.",
            self.ib_index,
        )
        # Rationale is signal-specific — no IB sections mapped
        assert len(results) == 0

    def test_conclusion_returns_no_ib(self):
        results = _resolve_ib_for_exec(
            "Conclusion",
            "Conclusion statement.",
            self.ib_index,
        )
        assert len(results) == 0

    def test_prefix_match_when_exact_missing(self):
        # If 4.3 is requested but only 4.3.3 exists, should do prefix match
        ib_index = {"4.3.3": "Toxicology subsection data."}
        results = _resolve_ib_for_exec(
            "Event of Interest",
            "Toxicology event.",
            ib_index,
        )
        # Should still find 4.3.3 via direct match
        labels = [label for label, _ in results]
        assert any("4.3.3" in l for l in labels)

    def test_table_reference_in_body(self):
        ib_index = {
            "5.5": "Clinical results including Table 30 data.",
        }
        results = _resolve_ib_for_exec(
            "Key Results",
            "See IB Table 30 for summary.",
            ib_index,
        )
        labels = [label for label, _ in results]
        assert any("Table 30" in l for l in labels), f"Expected Table 30, got {labels}"

    def test_no_duplicates_in_results(self):
        results = _resolve_ib_for_exec(
            "Data Sources and Key Results",
            "Data source methodology and results.",
            self.ib_index,
        )
        # Multiple keywords may match overlapping IB sections;
        # each section should appear only once
        seen_labels: set[str] = set()
        for label, _ in results:
            assert label not in seen_labels, f"Duplicate: {label}"
            seen_labels.add(label)
