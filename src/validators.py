"""10-check validation per SOP-SAF-001 step 5.8.

Each check returns (pass: bool, detail: str). The run_all function
executes all 10 and returns a summary.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import yaml

from .utils import logger, parse_scope, section_in_scope


class ValidationResult:
    def __init__(self) -> None:
        self.checks: list[tuple[int, str, bool, str]] = []

    def add(self, num: int, name: str, passed: bool, detail: str) -> None:
        self.checks.append((num, name, passed, detail))

    @property
    def all_passed(self) -> bool:
        return all(passed for _, _, passed, _ in self.checks)

    def summary(self) -> str:
        lines = ["Validation Results", "=" * 60]
        for num, name, passed, detail in self.checks:
            status = "PASS" if passed else "FAIL"
            lines.append(f"  [{status}] Check {num}: {name}")
            if detail:
                lines.append(f"         {detail}")
        lines.append("=" * 60)
        total = len(self.checks)
        passed_count = sum(1 for _, _, p, _ in self.checks if p)
        lines.append(f"  {passed_count}/{total} checks passed")
        return "\n".join(lines)


def run_all(
    template_text: str,
    source_rules_path: Path,
    mapping_path: Path,
    snapshot_path: Path,
    traced_dir: Path,
    scope_str: str,
    sections_dir: Path,
) -> ValidationResult:
    """Run all 10 validation checks."""
    result = ValidationResult()

    # Load files
    try:
        source_rules = yaml.safe_load(source_rules_path.read_text(encoding="utf-8"))
    except Exception as e:
        source_rules = None
        result.add(9, "File formats valid", False, f"source_rules YAML parse error: {e}")

    try:
        mapping_data = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    except Exception as e:
        mapping_data = None
        result.add(9, "File formats valid", False, f"mapping YAML parse error: {e}")

    try:
        with open(snapshot_path, encoding="utf-8") as f:
            snapshot_rows = list(csv.DictReader(f))
    except Exception as e:
        snapshot_rows = None
        result.add(9, "File formats valid", False, f"snapshot CSV parse error: {e}")

    scope = parse_scope(scope_str)

    # --- Check 1: Sources appear verbatim in template ---
    if source_rules:
        all_verbatim = True
        non_verbatim: list[str] = []
        for section in source_rules.get("template_sections", []):
            for src in section.get("required_sources", []):
                if src not in template_text:
                    all_verbatim = False
                    non_verbatim.append(f"{section.get('section_id')}: '{src}'")
        detail = "" if all_verbatim else f"Non-verbatim sources: {'; '.join(non_verbatim[:5])}"
        result.add(1, "Sources appear verbatim in template", all_verbatim, detail)
    else:
        result.add(1, "Sources appear verbatim in template", False, "Could not load source rules")

    # --- Check 2: No inferred sources ---
    # This is verified by Check 1 (verbatim check) + absence of sources not in template
    # We re-check that every source in the mapping's required_sources also appears in template
    if snapshot_rows is not None:
        inferred = []
        for row in snapshot_rows:
            sources = row.get("required_sources", "")
            if sources and sources != "N/A":
                for src in sources.split(", "):
                    src = src.strip()
                    if src and src not in template_text:
                        inferred.append(f"{row.get('dsr_section')}: '{src}'")
        passed = len(inferred) == 0
        detail = "" if passed else f"Possibly inferred: {'; '.join(inferred[:5])}"
        result.add(2, "No inferred sources", passed, detail)
    else:
        result.add(2, "No inferred sources", False, "Could not load snapshot")

    # --- Check 3: No content modification ---
    if traced_dir.exists():
        modified: list[str] = []
        for traced_file in sorted(traced_dir.glob("*.md")):
            original = _find_original(traced_file.name, sections_dir)
            if original is None:
                continue
            orig_content = original.read_text(encoding="utf-8")
            traced_content = traced_file.read_text(encoding="utf-8")
            # Strip SOURCE TRACE block from traced content
            stripped = re.sub(
                r"<!--\s*SOURCE\s+TRACE\s*\n.*?-->\s*\n*",
                "", traced_content, flags=re.DOTALL,
            ).lstrip("\n")
            # Strip SOURCE TRACE block from original (it may already have one)
            orig_stripped = re.sub(
                r"<!--\s*SOURCE\s+TRACE\s*\n.*?-->\s*\n*",
                "", orig_content, flags=re.DOTALL,
            ).lstrip("\n")
            if stripped != orig_stripped:
                modified.append(traced_file.name)
        passed = len(modified) == 0
        detail = "" if passed else f"Modified files: {', '.join(modified[:5])}"
        result.add(3, "No content modification", passed, detail)
    else:
        result.add(3, "No content modification", False, f"Traced dir not found: {traced_dir}")

    # --- Check 4: Unmapped sections marked consistently ---
    if mapping_data:
        inconsistent: list[str] = []
        for m in mapping_data.get("mappings", []):
            if m.get("template_section") is None:
                if m.get("match_method") != "no_match":
                    inconsistent.append(m.get("dsr_section", "?"))
        passed = len(inconsistent) == 0
        detail = "" if passed else f"Inconsistent unmapped: {', '.join(inconsistent)}"
        result.add(4, "Unmapped sections marked consistently", passed, detail)
    else:
        result.add(4, "Unmapped sections marked consistently", False, "Could not load mapping")

    # --- Check 5: Status only NOT VERIFIED or NOT MAPPED ---
    if snapshot_rows is not None:
        bad_status: list[str] = []
        for row in snapshot_rows:
            status = row.get("status", "")
            if status not in ("NOT VERIFIED", "NOT MAPPED"):
                bad_status.append(f"{row.get('dsr_section')}: '{status}'")
        passed = len(bad_status) == 0
        detail = "" if passed else f"Bad statuses: {'; '.join(bad_status[:5])}"
        result.add(5, "Status only NOT VERIFIED or NOT MAPPED", passed, detail)
    else:
        result.add(5, "Status only NOT VERIFIED or NOT MAPPED", False, "Could not load snapshot")

    # --- Check 6: All in-scope sections have trace blocks ---
    if mapping_data and traced_dir.exists():
        missing_trace: list[str] = []
        for m in mapping_data.get("mappings", []):
            dsn = m.get("dsr_section", "")
            if not section_in_scope(dsn, scope):
                continue
            dsr_file = m.get("dsr_file", "")
            filename = Path(dsr_file).name if dsr_file else ""
            if filename:
                traced = traced_dir / filename
                if not traced.exists():
                    missing_trace.append(dsn)
                else:
                    content = traced.read_text(encoding="utf-8")
                    if "<!-- SOURCE TRACE" not in content:
                        missing_trace.append(dsn)
        passed = len(missing_trace) == 0
        detail = "" if passed else f"Missing trace blocks: {', '.join(missing_trace)}"
        result.add(6, "All in-scope sections have trace blocks", passed, detail)
    else:
        result.add(6, "All in-scope sections have trace blocks", False, "Could not check")

    # --- Check 7: All in-scope sections in snapshot ---
    if mapping_data and snapshot_rows is not None:
        snapshot_sections = {row.get("dsr_section", "") for row in snapshot_rows}
        missing_snap: list[str] = []
        for m in mapping_data.get("mappings", []):
            dsn = m.get("dsr_section", "")
            if section_in_scope(dsn, scope) and dsn not in snapshot_sections:
                missing_snap.append(dsn)
        passed = len(missing_snap) == 0
        detail = "" if passed else f"Missing from snapshot: {', '.join(missing_snap)}"
        result.add(7, "All in-scope sections in snapshot", passed, detail)
    else:
        result.add(7, "All in-scope sections in snapshot", False, "Could not check")

    # --- Check 8: Scope distinction in mapping file ---
    if mapping_data:
        has_mappings = "mappings" in mapping_data
        has_future = "future_mappings" in mapping_data
        passed = has_mappings  # future_mappings is optional if all sections are in scope
        detail = f"mappings: {has_mappings}, future_mappings: {has_future}"
        result.add(8, "Scope distinction in mapping file", passed, detail)
    else:
        result.add(8, "Scope distinction in mapping file", False, "Could not load mapping")

    # --- Check 9: File formats valid ---
    # Already partially checked above during loading; confirm all loaded OK
    formats_ok = source_rules is not None and mapping_data is not None and snapshot_rows is not None
    if 9 not in [c[0] for c in result.checks]:
        result.add(9, "File formats valid", formats_ok,
                   "" if formats_ok else "One or more files failed to parse")

    # --- Check 10: Files in correct locations ---
    files_exist = (
        source_rules_path.exists()
        and mapping_path.exists()
        and snapshot_path.exists()
    )
    detail_parts = []
    if not source_rules_path.exists():
        detail_parts.append(f"Missing: {source_rules_path}")
    if not mapping_path.exists():
        detail_parts.append(f"Missing: {mapping_path}")
    if not snapshot_path.exists():
        detail_parts.append(f"Missing: {snapshot_path}")
    result.add(10, "Files in correct locations", files_exist, "; ".join(detail_parts))

    return result


def _find_original(filename: str, sections_dir: Path) -> Path | None:
    """Locate the original .md file in sections_dir."""
    candidate = sections_dir / filename
    if candidate.exists():
        return candidate
    nested = sections_dir / "dsr_sections" / filename
    if nested.exists():
        return nested
    return None
