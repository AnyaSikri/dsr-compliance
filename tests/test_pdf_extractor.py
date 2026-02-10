"""Tests for PDF extraction enhancements."""

from __future__ import annotations

from src.pdf_extractor import _strip_headers_footers


class TestStripHeadersFooters:
    def test_repeated_header_stripped(self) -> None:
        pages = [
            "Company Confidential\nActual content page 1",
            "Company Confidential\nActual content page 2",
            "Company Confidential\nActual content page 3",
            "Company Confidential\nActual content page 4",
        ]
        result = _strip_headers_footers(pages, threshold=3)
        for page in result:
            assert "Company Confidential" not in page

    def test_repeated_footer_stripped(self) -> None:
        pages = [
            "Content page 1\nPage 1 of 10",
            "Content page 2\nPage 1 of 10",
            "Content page 3\nPage 1 of 10",
        ]
        result = _strip_headers_footers(pages, threshold=3)
        for page in result:
            assert "Page 1 of 10" not in page

    def test_unique_lines_preserved(self) -> None:
        pages = [
            "Header\nUnique content A",
            "Header\nUnique content B",
            "Header\nUnique content C",
        ]
        result = _strip_headers_footers(pages, threshold=3)
        assert "Unique content A" in result[0]
        assert "Unique content B" in result[1]
        assert "Unique content C" in result[2]

    def test_below_threshold_not_stripped(self) -> None:
        pages = [
            "Header A\nContent 1",
            "Header B\nContent 2",
            "Header A\nContent 3",
        ]
        # "Header A" appears on 2 pages, threshold is 3
        result = _strip_headers_footers(pages, threshold=3)
        assert "Header A" in result[0]

    def test_fewer_pages_than_threshold(self) -> None:
        pages = ["Page 1 content", "Page 2 content"]
        result = _strip_headers_footers(pages, threshold=3)
        assert result == pages  # No stripping when < threshold pages

    def test_empty_pages_handled(self) -> None:
        pages = ["", "", ""]
        result = _strip_headers_footers(pages, threshold=3)
        assert len(result) == 3
