# DSR Compliance Generator

Generates Signal Assessment Reports from regulatory templates and Investigator's Brochure (IB) PDFs. Supports `.txt` and `.docx` templates, multi-source resolution (IB + PBRER + literature), and vector similarity matching.

## Quick Start (New Laptop)

Follow these steps in order to go from a fresh clone to a completed report.

### Step 1: Clone and install

```bash
git clone https://github.com/AnyaSikri/dsr-compliance.git
cd dsr-compliance
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 2: Set your OpenAI API key

```bash
export OPENAI_API_KEY="sk-your-key-here"
```

### Step 3: Place your files

Put your input files in `data/template/`:

```
data/template/
  dsr.pdf                              # Drug Safety Report PDF
  ib.pdf                               # Investigator's Brochure PDF
  pbrer.pdf                            # PBRER PDF (if you have one)
  signal_assessment_template.docx      # Template (.docx or .txt)
```

### Step 4: Build the PBRER index (only needed once per PBRER)

The PBRER is too large to process in full. Extract only the pages you need:

```bash
python -m src.pbrer_slicer --pbrer data/template/pbrer.pdf --pages "5:1-20, 5.1:21-45, 5.2:46-80" --output data/template/pbrer_index.json
```

The `--pages` format is `section_num:start_page-end_page`, comma-separated. Pages are 1-indexed. Adjust the page ranges to match your PBRER.

### Step 5: Run the pipeline

```bash
python -m src.cli from-pdf --pdf data/template/dsr.pdf --template data/template/signal_assessment_template.docx --ib data/template/ib.pdf --scope "1-6" --pbrer-index data/template/pbrer_index.json --output-dir data/mappings
```

### Step 6: Find your output

The filled report is in `data/output/`:

- `filled_template.md` -- markdown version
- `filled_template.docx` -- Word version

---

## Detailed Usage

There are two subcommands: `from-pdf` (extract sections from a DSR PDF) and `from-sections` (use pre-split `.md` section files).

### from-pdf

Use this when you have a raw DSR PDF.

```bash
python -m src.cli from-pdf --pdf data/template/dsr.pdf --template data/template/signal_assessment_template.docx --ib data/template/ib.pdf --scope "1-6" --pbrer-index data/template/pbrer_index.json --output-dir data/mappings
```

### from-sections

Use this when you already have extracted section `.md` files and an index CSV.

```bash
python -m src.cli from-sections --sections-dir data/input/dsr_sections/ --index-csv data/input/dsr_sections_index.csv --template data/template/signal_assessment_template.docx --ib data/template/ib.pdf --scope "1-6" --pbrer-index data/template/pbrer_index.json --output-dir data/mappings
```

### With literature sources

```bash
python -m src.cli from-pdf --pdf data/template/dsr.pdf --template data/template/signal_assessment_template.docx --ib data/template/ib.pdf --scope "1-6" --pbrer-index data/template/pbrer_index.json --literature data/input/literature.json --output-dir data/mappings
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
python -m src.cli from-pdf --pdf data/template/dsr.pdf --template data/template/signal_assessment_template.docx --ib data/template/ib.pdf --scope "1-6" --dry-run
```

### Disable vector matching

If you want keyword-only matching (no embeddings API calls):

```bash
python -m src.cli from-pdf --pdf data/template/dsr.pdf --template data/template/signal_assessment_template.docx --ib data/template/ib.pdf --scope "1-6" --no-vectors
```

### All options

| Flag | Description |
|------|-------------|
| `--pdf` | Path to DSR PDF (from-pdf only) |
| `--sections-dir` | Directory with `.md` section files (from-sections only) |
| `--index-csv` | Path to section index CSV (from-sections only) |
| `--template` | Path to regulatory template (`.txt` or `.docx`) |
| `--ib` | Path to Investigator's Brochure PDF |
| `--scope` | Section range, e.g. `"1-6"` |
| `--pbrer` | Path to PBRER PDF for auto-extraction (optional) |
| `--pbrer-index` | Path to pre-built PBRER index JSON from `pbrer_slicer` (optional) |
| `--literature` | Path to literature index JSON (optional) |
| `--no-vectors` | Disable vector similarity matching |
| `--model` | OpenAI model (default: `gpt-4o`) |
| `--output-dir` | Output directory (default: `data/mappings`) |
| `--dry-run` | Skip API calls, use placeholders |
| `--verbose` | Enable debug logging |

## Output

The pipeline generates these files:

- `data/output/filled_template.md` -- populated report in markdown
- `data/output/filled_template.docx` -- populated report in Word format
- `data/mappings/source_rules.yaml` -- extracted source rules per template section
- `data/mappings/section_mapping.yaml` -- DSR-to-template mapping with match methods
- `data/mappings/compliance_snapshot.csv` -- status of every section
- Traced `.md` files with `SOURCE TRACE` blocks for audit

## Running tests

```bash
python -m pytest tests/ -v
```

154 tests covering IB extraction, source resolution, template parsing, and report assembly.

## File structure

```
data/
  template/                 # Your input files go here
    dsr.pdf
    ib.pdf
    pbrer.pdf
    pbrer_index.json        # Generated by pbrer_slicer (Step 4)
    signal_assessment_template.docx
  output/                   # Generated reports appear here
  mappings/                 # Compliance deliverables appear here
src/
  cli.py                    # CLI entry point (from-pdf, from-sections)
  config.py                 # Configuration dataclass
  models.py                 # Pydantic data models
  pdf_extractor.py          # PDF section extraction + tables + OCR
  ib_extractor.py           # IB PDF indexing
  pbrer_extractor.py        # PBRER PDF indexing (auto-extraction)
  pbrer_slicer.py           # PBRER page slicer (targeted extraction)
  ib_resolver.py            # Source classification + multi-index resolution
  literature_resolver.py    # Clinical literature loader
  template_parser.py        # Template parsing (.txt/.docx) + mapping table
  section_mapper.py         # 4-pass section matching
  template_populator.py     # Filled report assembly (md + docx)
  vector_store.py           # FAISS + OpenAI embeddings
  chunker.py                # Token-aware text chunking
  deliverables.py           # Deliverable file generation
  validators.py             # 10-check validation suite
  utils.py                  # Logging and helpers
tests/
  test_*.py                 # 154 tests
```
