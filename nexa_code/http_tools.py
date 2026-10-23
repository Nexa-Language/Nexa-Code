"""Cancellable HTTP requests with bounded response capture and owned connections."""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any

import httpx
from src.runtime.tool_dispatch import ToolOutcomeUnknown

from .tool_services import current_session


def request(url: str, *, method: str = "GET", payload: Any = None, timeout: float = 20, limit: int = 2_000_000) -> dict[str, Any]:
    if httpx.URL(url).scheme not in {"https", "http"}:
        raise ValueError("HTTP tools require an http(s) URL")
    return asyncio.run(_request(url, method, payload, timeout, limit))


async def _request(url: str, method: str, payload: Any, timeout: float, limit: int) -> dict[str, Any]:
    session = current_session()
    end = min(session.deadline, time.monotonic() + timeout)

    async def operation() -> dict[str, Any]:
        async with (
            httpx.AsyncClient(timeout=max(0.01, end - time.monotonic()), follow_redirects=True) as client,
            client.stream(method, url, json=payload, headers={"User-Agent": "Nexa-Code/2.4"}) as response,
        ):
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=8192):
                body.extend(chunk[: max(0, limit - len(body))])
                if len(body) >= limit:
                    break
            return {"url": str(response.url), "status": response.status_code, "body": body.decode("utf-8", "replace")}

    task = asyncio.create_task(operation())
    try:
        while not task.done():
            if session.cancel.is_set() or time.monotonic() >= end:
                raise TimeoutError("HTTP request cancelled or deadline exceeded")
            await asyncio.wait({task}, timeout=0.025)
        return await task
    except (TimeoutError, httpx.HTTPError) as error:
        if method == "POST":
            raise ToolOutcomeUnknown("RemoteTrigger response unavailable after POST; inspect the remote effect before retrying") from error
        raise RuntimeError("HTTP request stopped: " + type(error).__name__) from error
    finally:
        task.cancel()
        # Retrieve task errors without masking the classified outcome above.
        with contextlib.suppress(asyncio.CancelledError, httpx.HTTPError):
            await task
