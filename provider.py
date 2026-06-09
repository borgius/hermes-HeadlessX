"""Hermes ``web.extract_backend`` provider backed by HeadlessX."""

from __future__ import annotations

import logging
import os
import socket
from typing import Any, Dict, List

from agent.web_search_provider import WebSearchProvider
from tools.website_policy import check_website_access

logger = logging.getLogger(__name__)

_CONTENT_PATH = "/api/operators/website/scrape/content"
_DEFAULT_API_URL = "http://127.0.0.1:38473"
_DEFAULT_TIMEOUT_SECONDS = 75.0


def _env(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _api_url() -> str:
    return _env("HEADLESSX_API_URL", "HX_API_URL") or _DEFAULT_API_URL


def _api_key() -> str:
    return _env("HEADLESSX_API_KEY", "HX_API_KEY")


def _timeout_seconds() -> float:
    raw = _env("HEADLESSX_TIMEOUT_SECONDS")
    if not raw:
        return _DEFAULT_TIMEOUT_SECONDS
    try:
        return max(1.0, float(raw))
    except ValueError:
        return _DEFAULT_TIMEOUT_SECONDS


def _error_message(response: Any) -> str:
    try:
        payload = response.json()
    except Exception:  # noqa: BLE001
        payload = None

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message:
                return message
            code = error.get("code")
            if isinstance(code, str) and code:
                return code
        if isinstance(error, str) and error:
            return error

    text = getattr(response, "text", "")
    if isinstance(text, str) and text.strip():
        return text.strip()[:500]
    return f"HTTP {response.status_code}"


def _connection_error_message(endpoint: str, exc: Exception) -> str:
    cause: BaseException | None = exc
    while cause is not None:
        if isinstance(cause, ConnectionRefusedError):
            return (
                f"HeadlessX is not reachable at {endpoint}. Start the self-hosted "
                "runtime with `headlessx start`, or set HEADLESSX_API_URL to a "
                "running HeadlessX API."
            )
        cause = cause.__cause__ or cause.__context__

    if isinstance(exc, (socket.gaierror, TimeoutError)):
        return f"HeadlessX is not reachable at {endpoint}: {exc}"
    return f"HeadlessX extraction failed: {exc}"


class HeadlessXWebSearchProvider(WebSearchProvider):
    """Extract web pages through a self-hosted HeadlessX API."""

    @property
    def name(self) -> str:
        return "headlessx"

    @property
    def display_name(self) -> str:
        return "HeadlessX"

    def is_available(self) -> bool:
        # HeadlessX protects extraction routes with x-api-key.
        return bool(_api_url() and _api_key())

    def supports_search(self) -> bool:
        return False

    def supports_extract(self) -> bool:
        return True

    def _extract_one(self, url: str, **kwargs: Any) -> Dict[str, Any]:
        import httpx

        options: Dict[str, Any] = {
            "stealth": kwargs.get("stealth", True),
        }
        timeout_ms = kwargs.get("timeout")
        if timeout_ms is not None:
            options["timeout"] = timeout_ms
        wait_for_selector = kwargs.get("wait_for_selector")
        if wait_for_selector:
            options["waitForSelector"] = wait_for_selector

        endpoint = f"{_api_url().rstrip('/')}{_CONTENT_PATH}"
        try:
            response = httpx.post(
                endpoint,
                json={"url": url, "options": options},
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": "hermes-HeadlessX/1.0",
                    "x-api-key": _api_key(),
                },
                timeout=_timeout_seconds(),
            )
        except httpx.RequestError as exc:
            raise RuntimeError(_connection_error_message(endpoint, exc)) from exc
        if not response.is_success:
            raise RuntimeError(
                f"HeadlessX returned HTTP {response.status_code}: "
                f"{_error_message(response)}"
            )

        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("HeadlessX returned a non-object JSON response")

        markdown = data.get("markdown")
        if not isinstance(markdown, str) or not markdown.strip():
            raise RuntimeError("HeadlessX returned no markdown content")

        final_url = data.get("url") if isinstance(data.get("url"), str) else url
        title = data.get("title") if isinstance(data.get("title"), str) else ""
        metadata = data.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        metadata = {
            **metadata,
            "sourceURL": final_url,
            "title": title,
            "provider": "headlessx",
        }

        return {
            "url": final_url,
            "title": title,
            "content": markdown,
            "raw_content": markdown,
            "metadata": metadata,
        }

    def extract(self, urls: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        from tools.interrupt import is_interrupted

        results: List[Dict[str, Any]] = []
        for url in urls:
            if is_interrupted():
                results.append(
                    {
                        "url": url,
                        "title": "",
                        "content": "",
                        "raw_content": "",
                        "error": "Interrupted",
                    }
                )
                continue

            blocked = check_website_access(url)
            if blocked:
                results.append(
                    {
                        "url": url,
                        "title": "",
                        "content": "",
                        "raw_content": "",
                        "error": blocked["message"],
                        "blocked_by_policy": {
                            "host": blocked["host"],
                            "rule": blocked["rule"],
                            "source": blocked["source"],
                        },
                    }
                )
                continue

            try:
                result = self._extract_one(url, **kwargs)
                final_blocked = check_website_access(result["url"])
                if final_blocked:
                    result.update(
                        {
                            "content": "",
                            "raw_content": "",
                            "error": final_blocked["message"],
                            "blocked_by_policy": {
                                "host": final_blocked["host"],
                                "rule": final_blocked["rule"],
                                "source": final_blocked["source"],
                            },
                        }
                    )
                results.append(result)
            except Exception as exc:  # noqa: BLE001
                logger.warning("HeadlessX extraction failed for %s: %s", url, exc)
                results.append(
                    {
                        "url": url,
                        "title": "",
                        "content": "",
                        "raw_content": "",
                        "error": str(exc)
                        if str(exc).startswith("HeadlessX")
                        else f"HeadlessX extraction failed: {exc}",
                    }
                )

        return results

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "HeadlessX",
            "badge": "self-hosted",
            "tag": "Browser-backed markdown extraction powered by Headfox JS and Camoufox.",
            "env_vars": [
                {
                    "key": "HEADLESSX_API_URL",
                    "prompt": "HeadlessX API URL",
                    "url": "https://github.com/saifyxpro/HeadlessX",
                },
                {
                    "key": "HEADLESSX_API_KEY",
                    "prompt": "HeadlessX API key",
                    "url": "https://headlessx.saify.me/docs/api-reference/overview",
                },
            ],
        }
