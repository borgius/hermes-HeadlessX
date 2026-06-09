from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HERMES_ROOT = Path(
    os.environ.get(
        "HERMES_AGENT_ROOT",
        str(Path.home() / ".hermes" / "hermes-agent"),
    )
)
sys.path.insert(0, str(HERMES_ROOT))
sys.path.insert(0, str(PLUGIN_ROOT))

import provider  # noqa: E402


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv("HEADLESSX_API_URL", "http://headlessx.test")
    monkeypatch.setenv("HEADLESSX_API_KEY", "test-key")
    monkeypatch.setattr(provider, "check_website_access", lambda _url: None)


def test_capabilities():
    instance = provider.HeadlessXWebSearchProvider()

    assert instance.name == "headlessx"
    assert instance.is_available()
    assert not instance.supports_search()
    assert instance.supports_extract()


def test_extract_normalizes_headlessx_response(monkeypatch):
    response = Mock(
        is_success=True,
        status_code=200,
    )
    response.json.return_value = {
        "url": "https://example.com/final",
        "title": "Example",
        "markdown": "# Example\n\nExtracted body.",
        "metadata": {"description": "A page"},
    }
    post = Mock(return_value=response)
    monkeypatch.setattr("httpx.post", post)

    result = provider.HeadlessXWebSearchProvider().extract(
        ["https://example.com"],
        format="markdown",
    )

    assert result == [
        {
            "url": "https://example.com/final",
            "title": "Example",
            "content": "# Example\n\nExtracted body.",
            "raw_content": "# Example\n\nExtracted body.",
            "metadata": {
                "description": "A page",
                "sourceURL": "https://example.com/final",
                "title": "Example",
                "provider": "headlessx",
            },
        }
    ]
    request = post.call_args
    assert request.args[0] == (
        "http://headlessx.test/api/operators/website/scrape/content"
    )
    assert request.kwargs["headers"]["x-api-key"] == "test-key"
    assert request.kwargs["json"]["url"] == "https://example.com"
    assert request.kwargs["json"]["options"]["stealth"] is True


def test_extract_returns_per_url_http_error(monkeypatch):
    response = Mock(
        is_success=False,
        status_code=401,
        text="",
    )
    response.json.return_value = {
        "error": {"code": "INVALID_API_KEY", "message": "Invalid API key"}
    }
    monkeypatch.setattr("httpx.post", Mock(return_value=response))

    result = provider.HeadlessXWebSearchProvider().extract(
        ["https://example.com"]
    )

    assert result[0]["url"] == "https://example.com"
    assert "HTTP 401" in result[0]["error"]
    assert "Invalid API key" in result[0]["error"]


def test_extract_honors_website_policy(monkeypatch):
    monkeypatch.setattr(
        provider,
        "check_website_access",
        lambda _url: {
            "host": "blocked.example",
            "rule": "deny",
            "source": "test",
            "message": "Blocked by policy",
        },
    )
    post = Mock()
    monkeypatch.setattr("httpx.post", post)

    result = provider.HeadlessXWebSearchProvider().extract(
        ["https://blocked.example"]
    )

    assert result[0]["error"] == "Blocked by policy"
    assert result[0]["blocked_by_policy"]["rule"] == "deny"
    post.assert_not_called()


def test_extract_reports_unreachable_runtime(monkeypatch):
    import httpx

    request = httpx.Request(
        "POST",
        "http://headlessx.test/api/operators/website/scrape/content",
    )

    def refuse(*args, **kwargs):
        error = ConnectionRefusedError(111, "Connection refused")
        raise httpx.ConnectError("Connection refused", request=request) from error

    monkeypatch.setattr("httpx.post", refuse)

    result = provider.HeadlessXWebSearchProvider().extract(
        ["https://example.com"]
    )

    assert result[0]["title"] == ""
    assert "HeadlessX is not reachable at http://headlessx.test/" in (
        result[0]["error"]
    )
    assert "`headlessx start`" in result[0]["error"]
