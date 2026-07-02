# SPDX-FileCopyrightText: 2026 Gary Frattarola <garyf@parkviewlab.ai>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Entry point for `cogrind-workshop` — the human-facing MCP client.

Pure MCP client. No business logic. No `App`. Wiki-operation flags
require a running `cobalt-grinding` daemon; if no daemon is reachable,
the CLI prints a clear error and exits with a non-zero status.

Flag surface:

- `cogrind-workshop --status` — call `wiki.status` and pretty-print
- `cogrind-workshop --index` / `--index-full` — submit `wiki.index`
- `cogrind-workshop --task-status <id>` — print state of a task
- `cogrind-workshop --task-list` — print recent tasks
- `cogrind-workshop --task-cancel <id>` — request cancellation
- `cogrind-workshop --ingest <path>` — call `wiki.ingest` (M3)
- `cogrind-workshop --query "..."` — call `wiki.search` (M4)
- `cogrind-workshop --ask "..."` — call `wiki.ask` (M5)
- `cogrind-workshop --find-gaps` — list open knowledge gaps (M4)
- `cogrind-workshop --report-gap "..."` — record a knowledge gap (M4)
- `cogrind-workshop --chat` — enter the interactive REPL (M5.5)

The REPL is single-turn-per-LLM-call for now: each user input runs
one `wiki.ask` round-trip. Multi-turn LLM context + token streaming
land in follow-up PRs (see `repl.py` module docstring).

Default daemon location is `127.0.0.1:7474` — the same defaults
cobalt-grinding ships with. Override with `--host` / `--port`. Future steps
may add config-file reading (`~/.config/cobalt_grinding/config.toml`) so the
CLI and daemon agree without flags.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import click
from rich.console import Console

from cogrind_workshop import __version__, formatters
from cogrind_workshop.client import (
    DaemonUnreachable,
    call_tool,
    stream_task,
)

console = Console()

# Defaults match cobalt-grinding's defaults. Keeping them in sync is a manual
# discipline for now; a future step may read both from a shared config
# file under ~/.config/cobalt_grinding/.
_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 7474


@click.command(name="cogrind-workshop")
@click.version_option(__version__, prog_name="cogrind-workshop")
@click.option(
    "--host",
    default=_DEFAULT_HOST,
    help=f"cobalt-grinding host (default: {_DEFAULT_HOST}).",
)
@click.option(
    "--port",
    default=_DEFAULT_PORT,
    type=int,
    help=f"cobalt-grinding port (default: {_DEFAULT_PORT}).",
)
@click.option("--status", "do_status", is_flag=True, help="Show daemon + wiki status.")
@click.option("--index", "do_index", is_flag=True, help="Run the indexer (incremental).")
@click.option("--index-full", "do_index_full", is_flag=True, help="Run the indexer with --full.")
@click.option(
    "--task-status",
    "task_status_id",
    default=None,
    help="Show state of one task by id.",
)
@click.option("--task-list", "do_task_list", is_flag=True, help="List recent tasks.")
@click.option(
    "--task-cancel",
    "task_cancel_id",
    default=None,
    help="Request cancellation of a task by id.",
)
@click.option(
    "--ingest",
    "ingest_path",
    default=None,
    type=click.Path(exists=False),  # daemon validates existence; CLI doesn't
    help="Ingest a file or directory into the Smalt (calls wiki.ingest).",
)
@click.option(
    "--query",
    "query_text",
    default=None,
    help="Search the wiki via hybrid retrieval (calls wiki.search).",
)
@click.option(
    "--ask",
    "ask_text",
    default=None,
    help="Ask a question; get a cited answer (calls wiki.ask).",
)
@click.option(
    "--find-gaps",
    "do_find_gaps",
    is_flag=True,
    help="List open knowledge gaps from the lab notebook (calls wiki.find_gaps).",
)
@click.option(
    "--report-gap",
    "report_gap_query",
    default=None,
    help="Record a knowledge gap to the lab notebook (calls wiki.report_gap).",
)
@click.option(
    "--chat",
    "do_chat",
    is_flag=True,
    help="Enter the interactive REPL (M5.5).",
)
@click.option(
    "--top-k",
    "top_k",
    default=None,
    type=int,
    help="Override default top-K for --query (default 10) or --ask (default 8).",
)
@click.option(
    "--expand-hops",
    "expand_hops",
    default=None,
    type=int,
    help="1-hop graph expansion for --query (default 0) or --ask (default 1).",
)
def main(
    host: str,
    port: int,
    do_status: bool,
    do_index: bool,
    do_index_full: bool,
    task_status_id: str | None,
    do_task_list: bool,
    task_cancel_id: str | None,
    ingest_path: str | None,
    query_text: str | None,
    ask_text: str | None,
    do_find_gaps: bool,
    report_gap_query: str | None,
    do_chat: bool,
    top_k: int | None,
    expand_hops: int | None,
) -> None:
    """cogrind-workshop — MCP client for the cobalt-grinding daemon."""
    actions = (
        do_status,
        do_index,
        do_index_full,
        task_status_id,
        do_task_list,
        task_cancel_id,
        ingest_path,
        query_text,
        ask_text,
        do_find_gaps,
        report_gap_query,
        do_chat,
    )
    flags_set = sum(bool(x) for x in actions)
    if flags_set == 0:
        console.print(
            "[yellow]No action specified.[/yellow]\n"
            "  --status / --index / --index-full\n"
            "  --task-status <id> / --task-list / --task-cancel <id>\n"
            "  --ingest <path> / --query <text> / --ask <question>\n"
            "  --find-gaps / --report-gap <query>\n"
            "  --chat   (interactive REPL)"
        )
        sys.exit(2)
    if flags_set > 1:
        console.print("[red]error[/red]: pass exactly one action flag at a time")
        sys.exit(2)

    try:
        if do_status:
            _do_status(host, port)
        elif do_index or do_index_full:
            _do_index(host, port, full=do_index_full)
        elif task_status_id:
            _do_task_status(host, port, task_status_id)
        elif do_task_list:
            _do_task_list(host, port)
        elif task_cancel_id:
            _do_task_cancel(host, port, task_cancel_id)
        elif ingest_path:
            _do_ingest(host, port, ingest_path)
        elif query_text:
            _do_query(host, port, query_text, top_k=top_k, expand_hops=expand_hops)
        elif ask_text:
            _do_ask(host, port, ask_text, top_k=top_k, expand_hops=expand_hops)
        elif do_find_gaps:
            _do_find_gaps(host, port)
        elif report_gap_query:
            _do_report_gap(host, port, report_gap_query)
        elif do_chat:
            _do_chat(host, port)
    except DaemonUnreachable as e:
        console.print(f"[red]error[/red]: {e}")
        sys.exit(3)


# ---- action handlers ----


def _do_status(host: str, port: int) -> None:
    result = call_tool("wiki.status", host=host, port=port)
    if not isinstance(result, dict):
        console.print(f"[red]unexpected response[/red]: {result!r}")
        sys.exit(4)
    formatters.format_status(result, console)


def _do_index(host: str, port: int, *, full: bool) -> None:
    seen_lines: set[str] = set()

    def on_update(task: dict[str, Any]) -> None:
        line = f"{task.get('status')}-{(task.get('progress') or {}).get('phase', '')}"
        if line not in seen_lines:
            seen_lines.add(line)
            formatters.format_progress_line(task, console)

    final = asyncio.run(
        stream_task(
            "wiki.index",
            {"full": full},
            on_update=on_update,
            host=host,
            port=port,
        )
    )
    formatters.format_index_result(final, console)


def _do_task_status(host: str, port: int, task_id: str) -> None:
    result = call_tool("wiki.task_status", {"task_id": task_id}, host=host, port=port)
    console.print_json(data=result)


def _do_task_list(host: str, port: int) -> None:
    result = call_tool("wiki.task_list", host=host, port=port)
    if not isinstance(result, list):
        console.print_json(data=result)
        return
    if not result:
        console.print("[dim]no tasks[/dim]")
        return
    from rich.table import Table

    table = Table(title="recent tasks")
    table.add_column("id")
    table.add_column("kind")
    table.add_column("status")
    table.add_column("submitted")
    table.add_column("finished")
    for t in result:
        table.add_row(
            t.get("id", "?"),
            t.get("kind", "?"),
            t.get("status", "?"),
            t.get("submitted_at", "?"),
            t.get("finished_at", "") or "",
        )
    console.print(table)


def _do_task_cancel(host: str, port: int, task_id: str) -> None:
    result = call_tool("wiki.task_cancel", {"task_id": task_id}, host=host, port=port)
    console.print_json(data=result)


def _do_ingest(host: str, port: int, path: str) -> None:
    """`wiki.ingest` is one synchronous-from-MCP-perspective call.

    For directory ingest the daemon may take a while (sub-agent
    pipeline per file); we await the response and render the summary.
    A streaming progress version would require background-task
    semantics on the daemon side — deferred.
    """
    result = call_tool("wiki.ingest", {"path": path}, host=host, port=port)
    if not isinstance(result, dict):
        console.print(f"[red]unexpected response[/red]: {result!r}")
        sys.exit(4)
    formatters.format_ingest_result(result, console)


def _do_query(host: str, port: int, query: str, *, top_k: int | None, expand_hops: int | None) -> None:
    args: dict[str, Any] = {"query": query}
    if top_k is not None:
        args["top_k"] = top_k
    if expand_hops is not None:
        args["expand_hops"] = expand_hops
    result = call_tool("wiki.search", args, host=host, port=port)
    if not isinstance(result, dict):
        console.print(f"[red]unexpected response[/red]: {result!r}")
        sys.exit(4)
    formatters.format_search_result(result, console)


def _do_ask(host: str, port: int, question: str, *, top_k: int | None, expand_hops: int | None) -> None:
    args: dict[str, Any] = {"question": question}
    if top_k is not None:
        args["top_k"] = top_k
    if expand_hops is not None:
        args["expand_hops"] = expand_hops
    result = call_tool("wiki.ask", args, host=host, port=port)
    if not isinstance(result, dict):
        console.print(f"[red]unexpected response[/red]: {result!r}")
        sys.exit(4)
    formatters.format_ask_result(result, console)


def _do_find_gaps(host: str, port: int) -> None:
    result = call_tool("wiki.find_gaps", host=host, port=port)
    if not isinstance(result, dict):
        console.print(f"[red]unexpected response[/red]: {result!r}")
        sys.exit(4)
    formatters.format_gaps_list(result, console)


def _do_report_gap(host: str, port: int, query: str) -> None:
    result = call_tool("wiki.report_gap", {"query": query}, host=host, port=port)
    if isinstance(result, dict) and result.get("error"):
        console.print(f"[red]error[/red]: {result.get('message', '?')}")
        sys.exit(4)
    if isinstance(result, dict):
        console.print(
            f"[green]gap recorded[/green]: id={result.get('gap_id', '?')} "
            f"position={result.get('position', '?')}"
        )
    else:
        console.print_json(data=result)


def _do_chat(host: str, port: int) -> None:
    """Enter the interactive REPL. Lazy-import keeps `prompt_toolkit`
    out of one-shot CLI invocations."""
    from cogrind_workshop import repl

    repl.run(host=host, port=port, console=console)


if __name__ == "__main__":
    main()
