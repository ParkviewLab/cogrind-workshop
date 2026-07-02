# SPDX-FileCopyrightText: 2026 Gary Frattarola <garyf@parkviewlab.ai>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Terminal output rendering for the cogrind-workshop CLI.

The CLI is just an MCP client; what makes it *feel* like a CLI lives here
— Rich tables, progress lines, colored status badges. Anything that
takes a tool-call result dict and prints something pretty.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.markup import escape
from rich.table import Table


def format_status(status: dict[str, Any], console: Console) -> None:
    """Pretty-print the result of `wiki.status`."""
    table = Table(title=f"cobalt-grinding — {status.get('wiki_dir', '?')}", show_header=False)
    table.add_column("key")
    table.add_column("value")

    table.add_row("version", str(status.get("version", "?")))
    table.add_row("milestone", str(status.get("milestone", "?")))
    # Be defensive: if a future / older daemon returns null for uptime, we
    # don't want the CLI to crash with a TypeError on `:.1f` format.
    uptime = status.get("daemon", {}).get("uptime_seconds")
    table.add_row("uptime (s)", f"{uptime:.1f}" if isinstance(uptime, int | float) else "?")
    table.add_row("wiki exists", _yes_no(bool(status.get("wiki_exists"))))
    table.add_row("pages indexed", str(status.get("pages_indexed", 0)))
    table.add_row("lance tables", ", ".join(status.get("lance_tables", []) or []))

    embed = status.get("embedding", {}) or {}
    table.add_row("embedding", f"{embed.get('provider')}:{embed.get('model')} (dim={embed.get('dim')})")

    mutex = status.get("corpus_mutex", {}) or {}
    if mutex.get("locked"):
        table.add_row("corpus mutex", f"[yellow]locked by {mutex.get('holder')}[/yellow]")
    else:
        table.add_row("corpus mutex", "[green]free[/green]")

    tasks = status.get("tasks", {}) or {}
    summary = ", ".join(f"{k}={v}" for k, v in tasks.items())
    table.add_row("tasks", summary)

    console.print(table)


def format_index_result(task: dict[str, Any], console: Console) -> None:
    """Pretty-print a finished `wiki.index` task."""
    final_status = task.get("status", "?")
    result = task.get("result", {}) or {}

    if final_status == "succeeded":
        console.print(
            f"\n[green]done[/green] in {result.get('duration_seconds', 0):.2f}s — "
            f"scanned {result.get('scanned', 0)}, "
            f"inserted {result.get('inserted', 0)}, "
            f"updated {result.get('updated', 0)}, "
            f"skipped {result.get('skipped', 0)}, "
            f"deleted {result.get('deleted', 0)}, "
            f"failed {result.get('failed', 0)}"
            f"{', cancelled' if result.get('cancelled') else ''}"
        )
        for path, msg in result.get("failures", []) or []:
            console.print(f"  [red]fail[/red] {path}: {msg}")
    elif final_status == "cancelled":
        console.print("[yellow]cancelled[/yellow]")
    else:
        console.print(f"[red]task {final_status}[/red]: {task.get('error', '?')}")


def format_progress_line(task: dict[str, Any], console: Console) -> None:
    """One-line progress update suitable for printing as a task is running."""
    status = task.get("status", "?")
    progress = task.get("progress") or {}
    if status == "running" and progress:
        bits = ", ".join(f"{k}={v}" for k, v in progress.items())
        console.print(f"  [dim]running[/dim] — {bits}")
    elif status == "queued":
        console.print("  [dim]queued[/dim]")


def format_ingest_result(result: dict[str, Any], console: Console) -> None:
    """Pretty-print a finished `wiki.ingest` response.

    The orchestrator returns `IngestResult.to_dict()` — source page id,
    section pages (multi-file), entity/glossary pages, link count, and
    skipped/error flags. We render a compact summary; full payload is
    available via `console.print_json(data=result)` if a user wants it.
    """
    if "error" in result:
        console.print(f"[red]ingest_error[/red]: {result.get('message', '?')}")
        return
    if result.get("skipped"):
        console.print(
            f"[yellow]skipped[/yellow] — {result.get('skip_reason', 'no-change')}: "
            f"{result.get('source_id', '?')}"
        )
        return

    table = Table(title="wiki.ingest", show_header=False)
    table.add_column("key")
    table.add_column("value")
    table.add_row("source id", str(result.get("source_id", "?")))
    table.add_row("page path", str(result.get("page_path", "?")))
    table.add_row("location", str(result.get("location_uri", "?")))
    table.add_row("kind", str(result.get("location_kind", "?")))
    table.add_row("files ingested", str(result.get("files_ingested", 0)))
    section_pages = result.get("section_pages_written") or []
    if section_pages:
        table.add_row("section pages", str(len(section_pages)))
    entities = result.get("entity_pages_written") or []
    if entities:
        table.add_row("entities written", str(len(entities)))
    glossary = result.get("glossary_pages_written") or []
    if glossary:
        table.add_row("glossary written", str(len(glossary)))
    table.add_row("links added", str(result.get("links_added", 0)))
    ignored = result.get("files_ignored") or []
    if ignored:
        truncated_marker = " (truncated)" if result.get("truncated") else ""
        table.add_row(
            f"ignored files{truncated_marker}",
            ", ".join(ignored[:6]) + (f", +{len(ignored) - 6} more" if len(ignored) > 6 else ""),
        )
    console.print(table)


def format_search_result(result: dict[str, Any], console: Console) -> None:
    """Pretty-print `wiki.search` response: ranked hits + optional expansion."""
    if "error" in result:
        console.print(f"[red]retrieve_error[/red]: {result.get('message', '?')}")
        return
    query = result.get("query", "")
    hits = result.get("hits") or []
    if not hits:
        console.print(f"[yellow]no hits[/yellow] for {query!r} — gap_detected")
        return

    table = Table(title=f"wiki.search — {query!r}")
    table.add_column("score", width=7)
    table.add_column("type", width=10)
    table.add_column("id")
    table.add_column("title")
    table.add_column("snippet", overflow="ellipsis", max_width=60)
    for h in hits:
        score = h.get("score", 0.0)
        table.add_row(
            f"{score:.2f}" if isinstance(score, int | float) else str(score),
            str(h.get("type", "?")),
            str(h.get("id", "?")),
            str(h.get("title", "?")),
            (h.get("snippet") or "").replace("\n", " "),
        )
    console.print(table)

    expanded = result.get("expanded_node_ids") or []
    if expanded:
        console.print(
            f"[dim]+ {len(expanded)} expanded node(s):[/dim] "
            + ", ".join(expanded[:6])
            + (f", +{len(expanded) - 6} more" if len(expanded) > 6 else "")
        )
    if result.get("truncated_expansion"):
        console.print("[dim](expansion truncated at smalt's per-hop cap)[/dim]")


def format_ask_result(result: dict[str, Any], console: Console) -> None:
    """Pretty-print `wiki.ask` response: cited answer + validation flags."""
    if "error" in result:
        console.print(f"[red]converse_error[/red]: {result.get('message', '?')}")
        return

    question = result.get("question", "")
    answer = result.get("answer", "")
    # `question` is user input and `answer` is LLM output — both opaque
    # text that may contain `[...]` patterns (notably `[page:<id>]`
    # citation tokens). Escape so rich doesn't interpret them as markup.
    console.print(f"[bold]Q:[/bold] {escape(question)}\n")
    console.print(f"[bold]A:[/bold] {escape(answer)}\n")

    citations = result.get("citations") or []
    if citations:
        console.print("[dim]citations:[/dim]")
        for c in citations:
            pid = c.get("page_id", "?")
            valid = c.get("valid", False)
            mark = "[green]✓[/green]" if valid else "[red]✗[/red]"
            console.print(f"  {mark} {escape(f'[page:{pid}]')}")
    invalid = result.get("invalid_citations") or []
    if invalid:
        joined = ", ".join(invalid)
        console.print(
            f"[red]warning[/red]: LLM cited {len(invalid)} page id(s) not in the "
            f"corpus — likely hallucination: {escape(joined)}"
        )
    if result.get("gap_detected"):
        console.print(
            "[yellow]gap_detected[/yellow] — the corpus didn't help. "
            'Consider `cogrind-workshop --report-gap "..."` to flag it for Research.'
        )
    if result.get("truncated_context"):
        console.print("[dim](some page bodies were truncated for the LLM context)[/dim]")


def format_gaps_list(result: dict[str, Any], console: Console) -> None:
    """Pretty-print `wiki.find_gaps` response: list of open knowledge gaps."""
    if "error" in result:
        console.print(f"[red]retrieve_error[/red]: {result.get('message', '?')}")
        return
    gaps = result.get("gaps") or []
    if not gaps:
        console.print("[green]no open gaps[/green]")
        return
    table = Table(title=f"open gaps ({len(gaps)})")
    table.add_column("id")
    table.add_column("query")
    table.add_column("created", overflow="ellipsis", max_width=20)
    table.add_column("why", overflow="ellipsis", max_width=30)
    for g in gaps:
        table.add_row(
            str(g.get("id", "?")),
            str(g.get("query", "?")),
            str(g.get("created_at", "?")),
            str(g.get("why", "") or ""),
        )
    console.print(table)


def _yes_no(b: bool) -> str:
    return "[green]yes[/green]" if b else "[red]no[/red]"
