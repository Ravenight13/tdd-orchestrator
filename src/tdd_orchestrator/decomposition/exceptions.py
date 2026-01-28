"""Exceptions for the decomposition module.

This module defines the exception hierarchy for spec decomposition operations,
following the error handling patterns established in the codebase.
"""

from __future__ import annotations


class DecompositionError(Exception):
    """Base exception for all decomposition-related errors.

    This is the root exception class for the decomposition module.
    All other decomposition exceptions inherit from this class.
    """

    pass


class SpecParseError(DecompositionError):
    """Raised when parsing of a spec file fails.

    This exception is raised when:
    - The spec file cannot be read or does not exist
    - The spec file has invalid format or structure
    - Required sections are missing or malformed
    """

    pass
