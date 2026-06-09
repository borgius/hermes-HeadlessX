"""HeadlessX extraction backend for Hermes Agent."""

from __future__ import annotations

try:
    from .provider import HeadlessXWebSearchProvider
except ImportError:
    # Allows direct pytest collection from the hyphenated repository directory.
    from provider import HeadlessXWebSearchProvider


def register(ctx) -> None:
    """Register the HeadlessX web extraction provider."""
    ctx.register_web_search_provider(HeadlessXWebSearchProvider())
