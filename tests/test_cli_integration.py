"""Integration tests for CLI argument parsing and pipeline wiring."""

from __future__ import annotations

import argparse

from src.cli import _add_common_enhancement_args, build_parser


class TestBuildParser:
    """Verify CLI parser accepts new enhancement arguments."""

    def test_from_sections_has_pbrer_arg(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "from-sections",
            "--sections-dir", "sections",
            "--index-csv", "index.csv",
            "--template", "template.txt",
            "--ib", "ib.pdf",
            "--scope", "1.1-1.2",
            "--pbrer", "pbrer.pdf",
        ])
        assert args.pbrer == "pbrer.pdf"

    def test_from_sections_has_literature_arg(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "from-sections",
            "--sections-dir", "sections",
            "--index-csv", "index.csv",
            "--template", "template.txt",
            "--ib", "ib.pdf",
            "--scope", "1.1-1.2",
            "--literature", "lit.json",
        ])
        assert args.literature == "lit.json"

    def test_from_sections_has_no_vectors_arg(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "from-sections",
            "--sections-dir", "sections",
            "--index-csv", "index.csv",
            "--template", "template.txt",
            "--ib", "ib.pdf",
            "--scope", "1.1-1.2",
            "--no-vectors",
        ])
        assert args.no_vectors is True

    def test_from_sections_defaults_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "from-sections",
            "--sections-dir", "sections",
            "--index-csv", "index.csv",
            "--template", "template.txt",
            "--ib", "ib.pdf",
            "--scope", "1.1-1.2",
        ])
        assert args.pbrer is None
        assert args.literature is None
        assert args.no_vectors is False

    def test_from_pdf_has_pbrer_arg(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "from-pdf",
            "--pdf", "dsr.pdf",
            "--template", "template.txt",
            "--ib", "ib.pdf",
            "--scope", "1.1-1.2",
            "--pbrer", "pbrer.pdf",
        ])
        assert args.pbrer == "pbrer.pdf"

    def test_from_pdf_has_literature_arg(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "from-pdf",
            "--pdf", "dsr.pdf",
            "--template", "template.txt",
            "--ib", "ib.pdf",
            "--scope", "1.1-1.2",
            "--literature", "lit.json",
        ])
        assert args.literature == "lit.json"

    def test_from_pdf_has_no_vectors_arg(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "from-pdf",
            "--pdf", "dsr.pdf",
            "--template", "template.txt",
            "--ib", "ib.pdf",
            "--scope", "1.1-1.2",
            "--no-vectors",
        ])
        assert args.no_vectors is True

    def test_from_pdf_defaults_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "from-pdf",
            "--pdf", "dsr.pdf",
            "--template", "template.txt",
            "--ib", "ib.pdf",
            "--scope", "1.1-1.2",
        ])
        assert args.pbrer is None
        assert args.literature is None
        assert args.no_vectors is False

    def test_all_new_args_combined(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "from-pdf",
            "--pdf", "dsr.pdf",
            "--template", "template.docx",
            "--ib", "ib.pdf",
            "--scope", "1.1-1.2",
            "--pbrer", "pbrer.pdf",
            "--literature", "lit.json",
            "--no-vectors",
        ])
        assert args.pbrer == "pbrer.pdf"
        assert args.literature == "lit.json"
        assert args.no_vectors is True
        assert args.template == "template.docx"


class TestAddCommonEnhancementArgs:
    """Verify the helper function adds the right arguments."""

    def test_adds_three_arguments(self) -> None:
        parser = argparse.ArgumentParser()
        _add_common_enhancement_args(parser)
        args = parser.parse_args(["--pbrer", "p.pdf", "--literature", "l.json", "--no-vectors"])
        assert args.pbrer == "p.pdf"
        assert args.literature == "l.json"
        assert args.no_vectors is True
