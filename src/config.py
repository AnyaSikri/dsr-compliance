"""Configuration loading from environment variables and .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Config:
    """Runtime configuration for the compliance deliverable generator."""

    openai_api_key: str = ""
    model: str = "gpt-4o"
    template_path: Path = field(default_factory=lambda: Path("data/templates/signal_assessment_template.txt"))
    sections_dir: Path = field(default_factory=lambda: Path("data/input"))
    index_csv: Path = field(default_factory=lambda: Path("data/input/dsr_sections_index.csv"))
    pdf_path: Path = field(default_factory=lambda: Path("data/input/dsr.pdf"))
    ib_path: Path = field(default_factory=lambda: Path("data/input/ib.pdf"))
    output_dir: Path = field(default_factory=lambda: Path("data/mappings"))
    intermediate_dir: Path = field(default_factory=lambda: Path("data/intermediate"))
    traced_output_dir: Path = field(default_factory=lambda: Path("data/output"))
    scope: str = ""
    dry_run: bool = False
    verbose: bool = False

    # Multi-source paths
    pbrer_path: Path = field(default_factory=lambda: Path("data/input/pbrer.pdf"))

    # Vectorization settings
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    vector_index_dir: Path = field(default_factory=lambda: Path("data/intermediate/vector_index"))
    chunk_size: int = 500
    chunk_overlap: int = 50

    # OCR settings
    ocr_enabled: bool = True

    @classmethod
    def from_env(cls, **overrides: object) -> Config:
        """Load config from environment / .env file, with CLI overrides."""
        load_dotenv()
        cfg = cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            model=str(overrides.get("model", os.getenv("OPENAI_MODEL", "gpt-4o"))),
        )
        for key, val in overrides.items():
            if val is not None and hasattr(cfg, key):
                setattr(cfg, key, val)
        return cfg

    def validate(self) -> list[str]:
        """Return list of validation errors (empty = OK)."""
        errors: list[str] = []
        if not self.openai_api_key and not self.dry_run:
            errors.append("OPENAI_API_KEY is not set. Export it or add to .env file.")
        if not self.template_path.exists():
            errors.append(f"Template file not found: {self.template_path}")
        return errors
