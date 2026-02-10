"""Tests for ib_extractor._sections_to_index."""

from __future__ import annotations

import pytest

from src.ib_extractor import _sections_to_index
from src.models import DSRSection


class TestSectionsToIndex:
    """Unit tests for _sections_to_index."""

    def test_basic_indexing(self) -> None:
        """Two distinct sections produce correct dict mapping."""
        sections = [
            DSRSection(
                section_num="1.1",
                title="Introduction",
                heading_full="1.1 Introduction",
                page_start=1,
                page_end=2,
                file="1.1_Introduction.md",
                content="This is the introduction.",
            ),
            DSRSection(
                section_num="2.1",
                title="Methods",
                heading_full="2.1 Methods",
                page_start=3,
                page_end=5,
                file="2.1_Methods.md",
                content="This section describes methods.",
            ),
        ]
        result = _sections_to_index(sections)
        assert result == {
            "1.1": "This is the introduction.",
            "2.1": "This section describes methods.",
        }

    def test_empty_sections(self) -> None:
        """Empty list of sections returns empty dict."""
        result = _sections_to_index([])
        assert result == {}

    def test_duplicate_section_num_keeps_last(self) -> None:
        """When duplicate section_num exists, last one wins."""
        sections = [
            DSRSection(
                section_num="3.1",
                title="Safety First Version",
                heading_full="3.1 Safety First Version",
                page_start=1,
                page_end=2,
                file="3.1_Safety_First_Version.md",
                content="First version of safety section.",
            ),
            DSRSection(
                section_num="3.1",
                title="Safety Revised",
                heading_full="3.1 Safety Revised",
                page_start=10,
                page_end=12,
                file="3.1_Safety_Revised.md",
                content="Revised safety section content.",
            ),
        ]
        result = _sections_to_index(sections)
        assert result == {"3.1": "Revised safety section content."}
