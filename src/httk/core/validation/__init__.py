"""Syntax validation predicates for IRIs and URLs."""

from .iris import has_valid_percent_escapes, is_absolute_iri, is_https_url, is_root_relative_url

__all__ = [
    "has_valid_percent_escapes",
    "is_absolute_iri",
    "is_https_url",
    "is_root_relative_url",
]
