"""Source classification and IB section lookup.

Classifies template source references (IB, PBRER, external databases)
and resolves IB references against a pre-built section index.
Includes text cleaning to strip boilerplate from extracted PDF content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Source text cleaning — strip boilerplate from extracted PDF content
# ---------------------------------------------------------------------------

_BOILERPLATE_PATTERNS = [
    # IB header lines (any drug name)
    re.compile(
        r"^Investigator's Brochure:.*$", re.MULTILINE
    ),
    # Confidentiality banners
    re.compile(r"^\s*CONFIDENTIAL\s*$", re.MULTILINE),
    # Version/date lines
    re.compile(
        r"^Version\s+Number\s+\d+,\s+\w+\s+\d{4}\s*$", re.MULTILINE
    ),
    # Standalone page numbers (e.g. "24" or "151" on their own line)
    re.compile(r"^\s*\d{1,3}\s*$", re.MULTILINE),
    # "X of Y" page footers (e.g. "24\n151" pattern — two consecutive number lines)
    re.compile(r"(?:^|\n)\s*\d{1,3}\s*\n\s*\d{1,3}\s*(?:\n|$)"),
    # PBRER header lines
    re.compile(
        r"^Periodic\s+Benefit[\-\u2010\u2013]Risk.*$", re.MULTILINE | re.IGNORECASE
    ),
]


def clean_source_text(text: str) -> str:
    """Strip boilerplate headers, footers, and page numbers from source text.

    Removes IB/PBRER confidentiality banners, version lines, and standalone
    page numbers that leak into extracted PDF content.
    """
    for pattern in _BOILERPLATE_PATTERNS:
        text = pattern.sub("", text)
    # Collapse runs of 3+ blank lines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# Regex for IB references with an optional "Section(s)" keyword and a dotted number.
# Accepts trailing parenthetical descriptions like "(Pharmacology/MoA)".
_IB_SECTION_RE = re.compile(
    r"^\s*IB\s*(?:Sections?\s*)?(\d+(?:\.\d+)*)\s*(?:\(.*\))?\s*$",
    re.IGNORECASE,
)

# Regex for "IB Table X" references.
_IB_TABLE_RE = re.compile(
    r"^\s*IB\s*Table\s*(\d+)",
    re.IGNORECASE,
)

# Regex for bare "IB" (no section number).
_IB_BARE_RE = re.compile(r"^\s*IB\s*$", re.IGNORECASE)

# Regex for PBRER references with an optional "Section(s)" keyword and a dotted number.
_PBRER_SECTION_RE = re.compile(
    r"^\s*PBRER\s*(?:Sections?\s*)?(\d+(?:\.\d+)*)\s*(?:\(.*\))?\s*$",
    re.IGNORECASE,
)

# Regex for compound references: "IB Sections 1.2, 3.2" or "IB Section 5.1, 5.6"
_COMPOUND_IB_RE = re.compile(
    r"^\s*IB\s*Sections?\s*([\d.,\s/&]+(?:\.\d+)*.*?)\s*(?:\(.*\))?\s*$",
    re.IGNORECASE,
)
_COMPOUND_PBRER_RE = re.compile(
    r"^\s*PBRER\s*(?:Sections?\s*)?([\d.,\s/&]+(?:\.\d+)*.*?)\s*(?:\(.*\))?\s*$",
    re.IGNORECASE,
)

# Known external source keywords (substring-matched, case-insensitive).
_EXTERNAL_KEYWORDS = [
    "uptodate",
    "medline",
    "embase",
    "company safety database",
    "signal assessment",
]


def _expand_compound_refs(ref: str) -> list[str]:
    """Expand compound source references into individual refs.

    Handles patterns like:
    - ``"IB Sections 1.2, 3.2"`` → ``["IB Section 1.2", "IB Section 3.2"]``
    - ``"IB Section 5.1, 5.6"`` → ``["IB Section 5.1", "IB Section 5.6"]``
    - ``"PBRER 1.1 & 1.2"`` → ``["PBRER 1.1", "PBRER 1.2"]``

    Returns a list of individual references.  If the input is not a
    compound reference (i.e. has only one section number), returns
    ``[ref]`` unchanged.
    """
    stripped = ref.strip()

    # Strip parenthetical descriptions for parsing
    cleaned = re.sub(r"\([^)]*\)", "", stripped).strip()

    # Check for IB compound pattern
    m = _COMPOUND_IB_RE.match(cleaned)
    if m:
        nums_str = m.group(1)
        # Split on comma, ampersand, slash, or "and"
        nums = re.split(r"[,&/]|\band\b", nums_str)
        result = []
        for n in nums:
            n = n.strip()
            if re.match(r"^\d+(?:\.\d+)*$", n):
                result.append(f"IB Section {n}")
        # Only expand if we found multiple numbers
        if len(result) > 1:
            return result

    # Check for PBRER compound pattern
    m = _COMPOUND_PBRER_RE.match(cleaned)
    if m:
        nums_str = m.group(1)
        nums = re.split(r"[,&/]|\band\b", nums_str)
        result = []
        for n in nums:
            n = n.strip()
            if re.match(r"^\d+(?:\.\d+)*$", n):
                result.append(f"PBRER {n}")
        # Only expand if we found multiple numbers
        if len(result) > 1:
            return result

    return [ref]


def classify_source(source: str) -> Tuple[str, Optional[str]]:
    """Classify a required_source string into a type and optional section number.

    Returns:
        A ``(source_type, section_number)`` tuple where *source_type* is one of
        ``"ib"``, ``"ib_table"``, ``"pbrer"``, ``"external"``, or ``"unknown"``; and
        *section_number* is a dotted-decimal string for IB/PBRER refs,
        a table number string for ``"ib_table"``, or ``None``.
    """
    # Try IB with section number first.
    m = _IB_SECTION_RE.match(source)
    if m:
        return ("ib", m.group(1))

    # IB Table reference (e.g. "IB Table 30").
    m = _IB_TABLE_RE.match(source)
    if m:
        return ("ib_table", m.group(1))

    # Bare IB.
    if _IB_BARE_RE.match(source):
        return ("ib", None)

    # PBRER with section number.
    m = _PBRER_SECTION_RE.match(source)
    if m:
        return ("pbrer", m.group(1))

    # Bare PBRER or PBRER with unstructured trailing text.
    stripped = source.strip()
    if stripped.lower().startswith("pbrer"):
        return ("pbrer", None)

    # Known external sources (substring match for flexibility).
    lower = stripped.lower()
    for kw in _EXTERNAL_KEYWORDS:
        if kw in lower:
            return ("external", None)

    return ("unknown", None)


@dataclass
class ResolvedSource:
    """Result of resolving a single source reference."""

    original_ref: str
    source_type: str
    section_num: Optional[str]
    content: str
    found: bool


def resolve_sources(
    required_sources: list[str],
    ib_index: dict[str, str],
    pbrer_index: dict[str, str] | None = None,
    literature_results: dict[str, str] | None = None,
) -> list[ResolvedSource]:
    """Resolve a list of source references against available indices.

    For IB references whose section number exists in *ib_index*, the
    corresponding text is returned with ``found=True``.  PBRER references
    are resolved against *pbrer_index* if provided.  External references
    are resolved against *literature_results* if provided.  All
    unresolvable references produce placeholder strings with ``found=False``.

    The optional ``pbrer_index`` and ``literature_results`` parameters
    preserve backward compatibility — existing callers that pass only
    ``ib_index`` will continue to work unchanged.
    """
    if not required_sources:
        return []

    # Expand compound references (e.g. "IB Sections 1.2, 3.2" → two refs)
    expanded: list[str] = []
    for ref in required_sources:
        expanded.extend(_expand_compound_refs(ref))

    results: list[ResolvedSource] = []
    for ref in expanded:
        source_type, section_num = classify_source(ref)

        if source_type == "ib_table":
            # Search the IB index for content containing "Table {num}"
            table_num = section_num
            found_content = None
            for sec_num, content in ib_index.items():
                if re.search(rf"\bTable\s*{re.escape(table_num)}\b", content):
                    found_content = content
                    break
            if found_content:
                results.append(
                    ResolvedSource(
                        original_ref=ref,
                        source_type="ib",
                        section_num=None,
                        content=clean_source_text(found_content),
                        found=True,
                    )
                )
            else:
                results.append(
                    ResolvedSource(
                        original_ref=ref,
                        source_type="ib",
                        section_num=None,
                        content=(
                            f"[ADDITIONAL DATA NEEDED: IB Table {table_num} "
                            f"was referenced but could not be located in the "
                            f"extracted IB content.]"
                        ),
                        found=False,
                    )
                )

        elif source_type == "ib":
            if section_num is not None:
                text = ib_index.get(section_num)
                if text is not None:
                    results.append(
                        ResolvedSource(
                            original_ref=ref,
                            source_type=source_type,
                            section_num=section_num,
                            content=clean_source_text(text),
                            found=True,
                        )
                    )
                else:
                    results.append(
                        ResolvedSource(
                            original_ref=ref,
                            source_type=source_type,
                            section_num=section_num,
                            content=(
                                f"[ADDITIONAL DATA NEEDED: IB Section {section_num} "
                                f"was referenced but not found in the extracted IB index. "
                                f"Provide the content from Investigator's Brochure section {section_num}.]"
                            ),
                            found=False,
                        )
                    )
            else:
                results.append(
                    ResolvedSource(
                        original_ref=ref,
                        source_type=source_type,
                        section_num=None,
                        content=(
                            "[ADDITIONAL DATA NEEDED: The Investigator's Brochure was "
                            "referenced without a specific section number. Review the IB "
                            "and provide the relevant content for this section.]"
                        ),
                        found=False,
                    )
                )

        elif source_type == "pbrer":
            if pbrer_index is not None and section_num is not None:
                text = pbrer_index.get(section_num)
                if text is not None:
                    results.append(
                        ResolvedSource(
                            original_ref=ref,
                            source_type=source_type,
                            section_num=section_num,
                            content=clean_source_text(text),
                            found=True,
                        )
                    )
                    continue
            # PBRER not resolved — produce descriptive placeholder
            if section_num:
                placeholder = (
                    f"[ADDITIONAL DATA NEEDED: PBRER Section {section_num} "
                    f"was referenced but could not be resolved. Provide the "
                    f"PBRER PDF via --pbrer flag or manually supply the content "
                    f"from PBRER section {section_num}.]"
                )
            else:
                placeholder = (
                    f"[ADDITIONAL DATA NEEDED: {ref.strip()} — provide the "
                    f"PBRER PDF via --pbrer flag or manually supply the "
                    f"relevant PBRER content for this section.]"
                )
            results.append(
                ResolvedSource(
                    original_ref=ref,
                    source_type=source_type,
                    section_num=section_num,
                    content=placeholder,
                    found=False,
                )
            )

        elif source_type == "external":
            if literature_results:
                # Try to match the reference against literature keys
                ref_lower = ref.strip().lower()
                for key, content in literature_results.items():
                    if key.lower() in ref_lower or ref_lower in key.lower():
                        results.append(
                            ResolvedSource(
                                original_ref=ref,
                                source_type=source_type,
                                section_num=None,
                                content=content,
                                found=True,
                            )
                        )
                        break
                else:
                    results.append(
                        ResolvedSource(
                            original_ref=ref,
                            source_type=source_type,
                            section_num=None,
                            content=(
                                f"[ADDITIONAL DATA NEEDED: External source '{ref.strip()}' "
                                f"was referenced but no matching entry was found in the "
                                f"literature index. Provide this data via --literature flag "
                                f"with a JSON file containing a '{ref.strip()}' key.]"
                            ),
                            found=False,
                        )
                    )
            else:
                results.append(
                    ResolvedSource(
                        original_ref=ref,
                        source_type=source_type,
                        section_num=None,
                        content=(
                            f"[ADDITIONAL DATA NEEDED: External source '{ref.strip()}' "
                            f"was referenced. Provide literature data via --literature "
                            f"flag with a JSON file containing a '{ref.strip()}' key.]"
                        ),
                        found=False,
                    )
                )

        else:
            # Unknown source type — provide descriptive placeholder.
            results.append(
                ResolvedSource(
                    original_ref=ref,
                    source_type=source_type,
                    section_num=None,
                    content=(
                        f"[ADDITIONAL DATA NEEDED: Source '{ref.strip()}' could not "
                        f"be classified or resolved. Manually provide the content "
                        f"for this reference.]"
                    ),
                    found=False,
                )
            )

    return results
