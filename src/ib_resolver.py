"""Source classification and IB section lookup.

Classifies template source references (IB, PBRER, external databases)
and resolves IB references against a pre-built section index.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple

# Regex for IB references with an optional "Section" keyword and a dotted number.
_IB_SECTION_RE = re.compile(
    r"^\s*IB\s*(?:Section\s*)?(\d+(?:\.\d+)*)\s*$",
    re.IGNORECASE,
)

# Regex for bare "IB" (no section number).
_IB_BARE_RE = re.compile(r"^\s*IB\s*$", re.IGNORECASE)

# Regex for PBRER references with an optional "Section" keyword and a dotted number.
_PBRER_SECTION_RE = re.compile(
    r"^\s*PBRER\s*(?:Section\s*)?(\d+(?:\.\d+)*)\s*$",
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


def classify_source(source: str) -> Tuple[str, Optional[str]]:
    """Classify a required_source string into a type and optional section number.

    Returns:
        A ``(source_type, section_number)`` tuple where *source_type* is one of
        ``"ib"``, ``"pbrer"``, ``"external"``, or ``"unknown"``; and
        *section_number* is a dotted-decimal string for IB refs or ``None``.
    """
    # Try IB with section number first.
    m = _IB_SECTION_RE.match(source)
    if m:
        return ("ib", m.group(1))

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

    results: list[ResolvedSource] = []
    for ref in required_sources:
        source_type, section_num = classify_source(ref)

        if source_type == "ib":
            if section_num is not None:
                text = ib_index.get(section_num)
                if text is not None:
                    results.append(
                        ResolvedSource(
                            original_ref=ref,
                            source_type=source_type,
                            section_num=section_num,
                            content=text,
                            found=True,
                        )
                    )
                else:
                    results.append(
                        ResolvedSource(
                            original_ref=ref,
                            source_type=source_type,
                            section_num=section_num,
                            content=f"[CONTENT NOT FOUND: {ref.strip()}]",
                            found=False,
                        )
                    )
            else:
                results.append(
                    ResolvedSource(
                        original_ref=ref,
                        source_type=source_type,
                        section_num=None,
                        content="[MANUAL INPUT REQUIRED: IB \u2014 no specific section referenced]",
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
                            content=text,
                            found=True,
                        )
                    )
                    continue
            # PBRER not resolved — produce placeholder
            results.append(
                ResolvedSource(
                    original_ref=ref,
                    source_type=source_type,
                    section_num=section_num,
                    content=f"[MANUAL INPUT REQUIRED: {ref.strip()}]",
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
                            content=f"[MANUAL INPUT REQUIRED: {ref.strip()}]",
                            found=False,
                        )
                    )
            else:
                results.append(
                    ResolvedSource(
                        original_ref=ref,
                        source_type=source_type,
                        section_num=None,
                        content=f"[MANUAL INPUT REQUIRED: {ref.strip()}]",
                        found=False,
                    )
                )

        else:
            # Unknown source type.
            results.append(
                ResolvedSource(
                    original_ref=ref,
                    source_type=source_type,
                    section_num=None,
                    content=f"[MANUAL INPUT REQUIRED: {ref.strip()}]",
                    found=False,
                )
            )

    return results
