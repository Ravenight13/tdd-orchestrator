"""Utility functions for spec decomposition.

This module provides helper functions for sanitizing content, chunking specs,
and other decomposition-related utilities.
"""

from __future__ import annotations

import re
from typing import Any


def sanitize_for_llm(content: str) -> str:
    """Remove XML-like angle bracket tags that cause empty SDK responses.

    The Claude Agent SDK CLI interprets angle bracket patterns specially,
    causing empty responses when prompts contain XML-like tags such as
    <requirement>, <acceptance-criteria>, <error-catalog>, etc.

    This function strips these tags while preserving the content structure.

    Args:
        content: Raw content potentially containing XML-like tags.

    Returns:
        Sanitized content safe for LLM prompts.

    Example:
        >>> sanitize_for_llm("<requirement id='FR-1'>Description</requirement>")
        "--- FR-1 ---\\nDescription\\n--- /FR-1 ---"
    """
    if not content:
        return content

    # Pattern to match XML-like opening tags with optional attributes
    # Matches: <tag>, <tag attr="value">, <tag attr='value'>
    opening_tag_pattern = re.compile(r"<(\w+[-\w]*)\s*(?:[^>]*)?>", re.IGNORECASE)

    # Pattern to match XML-like closing tags
    # Matches: </tag>
    closing_tag_pattern = re.compile(r"</(\w+[-\w]*)>", re.IGNORECASE)

    # Known semantic tags to convert to neutral delimiters
    semantic_tags = {
        "requirements",
        "requirement",
        "acceptance-criteria",
        "error-catalog",
        "testing",
        "implementation",
        "dependencies",
        "assumptions",
        "tdd-cycles",
        "typed-io",
    }

    def replace_opening_tag(match: re.Match[str]) -> str:
        tag_name = match.group(1).lower()
        if tag_name in semantic_tags:
            # Extract ID if present (e.g., <requirement id="FR-1">)
            full_match = match.group(0)
            id_match = re.search(r'id=["\']([^"\']+)["\']', full_match)
            if id_match:
                return f"--- {id_match.group(1)} ---\n"
            return f"=== {tag_name.upper().replace('-', '_')} ===\n"
        # For unrecognized tags, just remove them
        return ""

    def replace_closing_tag(match: re.Match[str]) -> str:
        tag_name = match.group(1).lower()
        if tag_name in semantic_tags:
            # Check if this was an ID-based tag
            return f"--- /{tag_name.upper()} ---\n"
        return ""

    # Apply transformations
    result = opening_tag_pattern.sub(replace_opening_tag, content)
    result = closing_tag_pattern.sub(replace_closing_tag, result)

    # Clean up excessive newlines
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result


def chunk_spec_by_cycles(
    content: str,
    tdd_cycles: list[dict[str, Any]],
    max_chunk_size: int = 40000,
) -> list[dict[str, Any]]:
    """Split a large spec into chunks organized by TDD cycles.

    Each chunk contains:
    - The TDD cycle metadata
    - Relevant FRs linked to that cycle's components
    - Related acceptance criteria

    This enables the decomposer to process large specs incrementally
    without overwhelming the SDK.

    Args:
        content: Raw spec content.
        tdd_cycles: List of extracted TDD cycles from the parser.
        max_chunk_size: Maximum characters per chunk (default 40KB).

    Returns:
        List of chunk dictionaries with cycle, frs, and acs keys.

    Example:
        >>> chunks = chunk_spec_by_cycles(content, cycles)
        >>> len(chunks)
        5
        >>> chunks[0]["cycle"]["cycle_number"]
        1
    """
    if not tdd_cycles:
        # No cycles - return single chunk with full content
        return [{"cycle": None, "content": content[:max_chunk_size]}]

    chunks: list[dict[str, Any]] = []

    for cycle in tdd_cycles:
        cycle_num = cycle.get("cycle_number", 0)
        components = cycle.get("components", [])
        phase = cycle.get("phase", "")

        # Extract section of content related to this cycle
        # Start from cycle definition, end at next cycle or section
        cycle_start_pattern = rf"TDD Cycle {cycle_num}:"
        start_match = re.search(cycle_start_pattern, content, re.IGNORECASE)

        if start_match:
            start_pos = start_match.start()
            # Find the end (next cycle or major section)
            end_pattern = rf"(?:TDD Cycle {cycle_num + 1}:|={(20,)})"
            end_match = re.search(end_pattern, content[start_pos + 100 :])
            end_pos = start_pos + 100 + end_match.start() if end_match else len(content)

            cycle_content = content[start_pos:end_pos]

            # Limit chunk size
            if len(cycle_content) > max_chunk_size:
                cycle_content = cycle_content[:max_chunk_size]

            chunks.append(
                {
                    "cycle": cycle,
                    "cycle_number": cycle_num,
                    "phase": phase,
                    "components": components,
                    "content": cycle_content,
                }
            )
        else:
            # Cycle not found in content, use metadata only
            chunks.append(
                {
                    "cycle": cycle,
                    "cycle_number": cycle_num,
                    "phase": phase,
                    "components": components,
                    "content": "",
                }
            )

    return chunks


def extract_frs_for_components(
    content: str,
    components: list[str],
) -> list[dict[str, str]]:
    """Extract FRs that mention specific components.

    Scans through FR sections to find requirements that reference
    any of the given component names.

    Args:
        content: Spec content containing FR sections.
        components: List of component names to search for.

    Returns:
        List of FR dictionaries with id, title, and content.
    """
    if not components:
        return []

    frs: list[dict[str, str]] = []
    fr_pattern = re.compile(r"FR-(\d+):\s*(.+?)(?=FR-\d+:|={20,}|$)", re.DOTALL)

    for match in fr_pattern.finditer(content):
        fr_id = f"FR-{match.group(1)}"
        fr_content = match.group(2).strip()

        # Check if any component is mentioned in this FR
        for comp in components:
            if comp.lower() in fr_content.lower():
                # Extract just the title (first line)
                lines = fr_content.split("\n")
                title = lines[0].strip() if lines else ""

                frs.append(
                    {
                        "id": fr_id,
                        "title": title,
                        "content": fr_content[:2000],  # Limit content size
                    }
                )
                break

    return frs


def estimate_token_count(text: str) -> int:
    """Estimate token count for text (rough approximation).

    Uses a simple heuristic: ~4 characters per token.
    This is a rough estimate for Claude tokenization.

    Args:
        text: Text to estimate tokens for.

    Returns:
        Estimated token count.
    """
    if not text:
        return 0
    # Rough estimate: ~4 chars per token for English text
    return len(text) // 4
