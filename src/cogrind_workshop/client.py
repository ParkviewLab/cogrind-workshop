# SPDX-FileCopyrightText: 2026 Gary Frattarola <garyf@parkviewlab.ai>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""MCP-over-HTTP client used by the `cogrind-workshop` CLI.

Wraps the official `mcp` SDK's `streamable_http_client` + `ClientSession`
in a small synchronous-feeling helper so the CLI's flag handlers don't
each have to drive an asyncio loop.

This module is pure transport — no rendering, no wiki-specific logic.
The CLI in `cogrind_workshop.main` consumes it; tests can target this
module against any MCP server (stub or real).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


class DaemonUnreachable(RuntimeError):
    """Raised when no `cobalt-grinding` daemon is reachable at the configured URL."""


def _mcp_url(host: str, port: int) -> str:
    return f"http://{host}:{port}/mcp"


def _is_connection_error(exc: BaseException) -> bool:
    """Recognize the various ways 'daemon not listening' surfaces.

    httpx wraps low-level connection errors; anyio (used by streamable-http)
    can group them inside a BaseExceptionGroup. We walk the tree to check.
    """
    if isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout | ConnectionError | OSError):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_is_connection_error(e) for e in exc.exceptions)
    cause = exc.__cause__ or exc.__context__
    return cause is not None and _is_connection_error(cause)


@asynccontextmanager
async def _session(host: str, port: int) -> AsyncIterator[ClientSession]:
    """Open an MCP session over streamable-HTTP and yield the ClientSession."""
    url = _mcp_url(host, port)
    try:
        async with (
            streamable_http_client(url) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            yield session
    except BaseException as e:
        if _is_connection_error(e):
            raise DaemonUnreachable(
                f"could not reach cobalt-grinding at {url} — start one with: cobalt-grinding"
            ) from e
        raise


def call_tool(
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 7474,
) -> Any:
    """Synchronous helper: connect, call one tool, decode the result, disconnect.

    The MCP `call_tool` returns content blocks; for cobalt-grinding's tools the
    first block is JSON text. This function extracts that and parses it.

    Note: each call opens a fresh MCP session (HTTP connect + initialize
    handshake). For one-shot CLI invocations (`cogrind-workshop --status`)
    this is fine — startup cost dominates anyway. A future REPL form will
    keep a single session open across many tool calls.
    """
    return asyncio.run(_call_tool_async(name, arguments or {}, host=host, port=port))


async def _call_tool_async(name: str, arguments: dict[str, Any], *, host: str, port: int) -> Any:
    async with _session(host, port) as session:
        result = await session.call_tool(name, arguments)
        return _decode(result)


def _decode(result: Any) -> Any:
    """Pull the first text content block out of a tool-call result and JSON-decode it."""
    content = getattr(result, "content", None)
    if not content:
        return None
    first = content[0]
    text = getattr(first, "text", None)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


# ---- streaming helper for tail-progress style flows ----


async def stream_task(
    submit_tool: str,
    submit_args: dict[str, Any],
    *,
    on_update: Callable[[dict[str, Any]], None],
    poll_interval: float = 0.25,
    timeout_seconds: float | None = None,
    host: str = "127.0.0.1",
    port: int = 7474,
) -> dict[str, Any]:
    """Submit a long-running tool, poll status, return final task dict.

    `on_update` is called every poll iteration with the current task dict
    so the caller can render progress.
    """
    async with _session(host, port) as session:
        submit_result = _decode(await session.call_tool(submit_tool, submit_args))
        task_id = submit_result.get("task_id") if isinstance(submit_result, dict) else None
        if not task_id:
            raise RuntimeError(f"{submit_tool} did not return a task_id; got: {submit_result!r}")

        elapsed = 0.0
        while True:
            status = _decode(await session.call_tool("wiki.task_status", {"task_id": task_id}))
            if not isinstance(status, dict):
                raise RuntimeError(f"unexpected task_status payload: {status!r}")
            on_update(status)
            if status.get("status") in ("succeeded", "failed", "cancelled"):
                return status
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            if timeout_seconds is not None and elapsed > timeout_seconds:
                raise TimeoutError(f"task {task_id} did not finish within {timeout_seconds}s")
