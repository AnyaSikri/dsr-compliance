# DSR Compliance Generator

Generates Signal Assessment Reports from regulatory templates and Investigator's Brochure (IB) PDFs. Supports `.txt` and `.docx` templates, multi-source resolution (IB + PBRER + literature), and vector similarity matching.

## Setup

### 1. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Export your OpenAI API key

```bash
export OPENAI_API_KEY="sk-your-key-here"
```

## Usage

There are two subcommands: `from-pdf` (extract sections from a DSR PDF) and `from-sections` (use pre-split `.md` section files).

### from-pdf

Use this when you have a raw DSR PDF.

```bash
python -m src.cli from-pdf \
  --pdf data/input/dsr.pdf \
  --template data/templates/signal_assessment_template.txt \
  --ib data/input/ib.pdf \
  --scope "1.1-3.3.1"
```

### from-sections

Use this when you already have extracted section `.md` files and an index CSV.

```bash
python -m src.cli from-sections \
  --sections-dir data/input/dsr_sections/ \
  --index-csv data/input/dsr_sections_index.csv \
  --template data/templates/signal_assessment_template.txt \
  --ib data/input/ib.pdf \
  --scope "1.1-3.3.1"
```

### With a .docx template

Both commands accept `.docx` templates. If the `.docx` contains a mapping table, it will be parsed automatically.

```bash
python -m src.cli from-pdf \
  --pdf data/input/dsr.pdf \
  --template data/templates/signal_assessment_template.docx \
  --ib data/input/ib.pdf \
  --scope "1.1-3.3.1"
```

### With PBRER and literature sources

```bash
python -m src.cli from-pdf \
  --pdf data/input/dsr.pdf \
  --template data/templates/signal_assessment_template.docx \
  --ib data/input/ib.pdf \
  --scope "1.1-3.3.1" \
  --pbrer data/input/pbrer.pdf \
  --literature data/input/literature.json
```

The literature JSON file should look like:

```json
{
  "Medline": "Summary of Medline search results...",
  "Embase": "Summary of Embase findings...",
  "UpToDate": "Clinical summary from UpToDate..."
}
```

### Dry run (no API calls)

```bash
python -m src.cli from-pdf \
  --pdf data/input/dsr.pdf \
  --template data/templates/signal_assessment_template.txt \
  --ib data/input/ib.pdf \
  --scope "1.1-3.3.1" \
  --dry-run
```

### Disable vector matching

If you want keyword-only matching (no embeddings API calls):

```bash
python -m src.cli from-pdf \
  --pdf data/input/dsr.pdf \
  --template data/templates/signal_assessment_template.txt \
  --ib data/input/ib.pdf \
  --scope "1.1-3.3.1" \
  --no-vectors
```

### All options

| Flag | Description |
|------|-------------|
| `--pdf` | Path to DSR PDF (from-pdf only) |
| `--sections-dir` | Directory with `.md` section files (from-sections only) |
| `--index-csv` | Path to section index CSV (from-sections only) |
| `--template` | Path to regulatory template (`.txt` or `.docx`) |
| `--ib` | Path to Investigator's Brochure PDF |
| `--scope` | Section range, e.g. `"1.1-3.3.1"` |
| `--pbrer` | Path to PBRER PDF (optional) |
| `--literature` | Path to literature index JSON (optional) |
| `--no-vectors` | Disable vector similarity matching |
| `--model` | OpenAI model (default: `gpt-4o`) |
| `--output-dir` | Output directory (default: `data/mappings`) |
| `--dry-run` | Skip API calls, use placeholders |
| `--verbose` | Enable debug logging |

## Output

The pipeline generates these files in the output directory:

- `source_rules.yaml` -- extracted source rules per template section
- `section_mapping.yaml` -- DSR-to-template mapping with match methods
- `compliance_snapshot.csv` -- status of every section
- `filled_template.md` -- populated report in markdown
- `filled_template.docx` -- populated report in Word format
- Traced `.md` files with `SOURCE TRACE` blocks for audit

## Running tests

```bash
python -m pytest tests/ -v
```

## File structure

```
src/
  cli.py              # CLI entry point (from-pdf, from-sections)
  config.py           # Configuration dataclass
  models.py           # Pydantic data models
  pdf_extractor.py    # PDF section extraction + tables + OCR
  ib_extractor.py     # IB PDF indexing
  pbrer_extractor.py  # PBRER PDF indexing
  ib_resolver.py      # Source classification + multi-index resolution
  literature_resolver.py  # Clinical literature loader
  template_parser.py  # Template parsing (.txt/.docx) + mapping table
  section_mapper.py   # 4-pass section matching
  template_populator.py   # Filled report assembly (md + docx)
  vector_store.py     # FAISS + OpenAI embeddings
  chunker.py          # Token-aware text chunking
  deliverables.py     # Deliverable file generation
  validators.py       # 10-check validation suite
  utils.py            # Logging and helpers
tests/
  test_*.py           # 125 tests
```
