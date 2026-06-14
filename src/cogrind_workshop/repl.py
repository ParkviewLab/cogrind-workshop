# SPDX-FileCopyrightText: 2026 Gary Frattarola <garyf@parkviewlab.ai>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Interactive REPL for cogrind-workshop — `cogrind-workshop --chat`.

The conversational interface. `prompt_toolkit` for line editing +
history; slash commands for non-conversational operations inside the
shell; bare-text turns go to `wiki.ask` and the cited answer
pretty-prints.

**First-cut scope (M5.5 first impl):**

- One-shot `wiki.ask` per turn — each question is independent. The
  REPL does NOT yet feed prior turns to the LLM as conversation
  context; that requires extending `wiki.ask`'s daemon-side surface
  to accept a `messages` history (a future enhancement).
- No token streaming yet — the daemon's `wiki.ask` returns the full
  answer in one MCP tool result. A spinner shows during the call.
  Token streaming requires daemon-side protocol work (see the
  M2.5 "streaming response shape" deferred seam).
- Slash commands: `/quit`, `/help`, `/clear`, `/history`,
  `/status`, `/search <query>`, `/page <id>`, `/gaps`,
  `/report-gap <query>`, `/ingest <path>`.

**Future enhancements** (separable PRs):
- Multi-turn LLM context (extend `wiki.ask` to accept prior turns).
- Token streaming (extend `wiki.ask` to use MCP `notifications/progress`).
- Session save/restore via ConversationPages.
- Voice in/out as a separate sibling project.
"""

from __future__ import annotations

from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console
from rich.markup import escape

from cogrind_workshop import formatters
from cogrind_workshop.client import DaemonUnreachable, call_tool

# Slash commands dispatch table (user help + parser).
#
# Each value is `(description, handler)`. Handler signature:
#   handler(args: str, host: str, port: int, console: Console,
#           messages_log: list[dict[str, str]]) -> bool
# Return True to exit the REPL; False to keep looping.
#
# `args` is everything after the slash command name (already
# whitespace-stripped). Handlers parse further as they need.
# `messages_log` is the multi-turn conversation history (user + assistant
# turns) the REPL maintains across `wiki.ask` calls. Handlers that
# don't need it can ignore it.


def _help_text() -> str:
    """The /help output. Built dynamically so adding a slash command
    only requires adding one entry to `_SLASH_COMMANDS` below."""
    lines = ["[bold]Commands:[/bold]"]
    for name, (desc, _) in _SLASH_COMMANDS.items():
        lines.append(f"  [dim]{name:<24}[/dim] {desc}")
    lines.append("")
    lines.append("Any non-`/` input is sent as a question to `wiki.ask`.")
    return "\n".join(lines)


# ---- slash command handlers ----


def _cmd_quit(
    _args: str, _host: str, _port: int, console: Console, _log: list[dict[str, str]]
) -> bool:
    console.print("[dim]bye[/dim]")
    return True


def _cmd_help(
    _args: str, _host: str, _port: int, console: Console, _log: list[dict[str, str]]
) -> bool:
    console.print(_help_text())
    return False


def _cmd_clear(
    _args: str, _host: str, _port: int, console: Console, _log: list[dict[str, str]]
) -> bool:
    console.clear()
    return False


def _cmd_history(
    _args: str, _host: str, _port: int, console: Console, log: list[dict[str, str]]
) -> bool:
    """Show this session's user questions. Filters the multi-turn
    message log to just the user-role entries."""
    questions = [m.get("content", "") for m in log if m.get("role") == "user"]
    if not questions:
        console.print("[dim]no questions asked this session[/dim]")
        return False
    for i, q in enumerate(questions, start=1):
        console.print(f"  [dim]{i}.[/dim] {escape(q)}")
    return False


def _cmd_reset(
    _args: str, _host: str, _port: int, console: Console, log: list[dict[str, str]]
) -> bool:
    """Clear the multi-turn conversation history without exiting.

    Useful when you're switching topics and don't want the next
    question to be biased by earlier context. The REPL keeps running;
    `/history` afterwards shows an empty list.
    """
    count = sum(1 for m in log if m.get("role") == "user")
    log.clear()
    if count:
        console.print(f"[green]reset[/green] — cleared {count} prior turn(s)")
    else:
        console.print("[dim]nothing to reset[/dim]")
    return False


def _cmd_status(
    _args: str, host: str, port: int, console: Console, _log: list[dict[str, str]]
) -> bool:
    result = _safe_call_tool(console, "wiki.status", host=host, port=port)
    if result is None:
        return False
    if not isinstance(result, dict):
        console.print(f"[red]unexpected response[/red]: {result!r}")
        return False
    formatters.format_status(result, console)
    return False


def _cmd_search(
    args: str, host: str, port: int, console: Console, _log: list[dict[str, str]]
) -> bool:
    query = args.strip()
    if not query:
        console.print("[red]usage[/red]: /search <query>")
        return False
    result = _safe_call_tool(
        console, "wiki.search", {"query": query}, host=host, port=port
    )
    if result is None:
        return False
    if not isinstance(result, dict):
        console.print(f"[red]unexpected response[/red]: {result!r}")
        return False
    formatters.format_search_result(result, console)
    return False


def _cmd_page(
    args: str, host: str, port: int, console: Console, _log: list[dict[str, str]]
) -> bool:
    page_id = args.strip()
    if not page_id:
        console.print("[red]usage[/red]: /page <id>")
        return False
    result = _safe_call_tool(
        console, "wiki.get_page", {"page_id": page_id}, host=host, port=port
    )
    if result is None:
        return False
    if isinstance(result, dict) and "error" in result:
        console.print(f"[red]{result['error']}[/red]: {result.get('message', '?')}")
        return False
    if isinstance(result, dict):
        title = result.get("title") or result.get("id", page_id)
        console.print(f"[bold]{escape(str(title))}[/bold]  [dim]({escape(page_id)})[/dim]")
        console.print()
        body = result.get("body", "")
        console.print(escape(str(body)))
    else:
        console.print(f"[red]unexpected response[/red]: {result!r}")
    return False


def _cmd_gaps(
    _args: str, host: str, port: int, console: Console, _log: list[dict[str, str]]
) -> bool:
    result = _safe_call_tool(console, "wiki.find_gaps", host=host, port=port)
    if result is None:
        return False
    if not isinstance(result, dict):
        console.print(f"[red]unexpected response[/red]: {result!r}")
        return False
    formatters.format_gaps_list(result, console)
    return False


def _cmd_report_gap(
    args: str, host: str, port: int, console: Console, _log: list[dict[str, str]]
) -> bool:
    query = args.strip()
    if not query:
        console.print("[red]usage[/red]: /report-gap <query>")
        return False
    result = _safe_call_tool(
        console, "wiki.report_gap", {"query": query}, host=host, port=port
    )
    if result is None:
        return False
    if isinstance(result, dict) and result.get("error"):
        console.print(f"[red]error[/red]: {result.get('message', '?')}")
        return False
    if isinstance(result, dict):
        console.print(
            f"[green]gap recorded[/green]: id={result.get('gap_id', '?')} "
            f"position={result.get('position', '?')}"
        )
    return False


def _cmd_ingest(
    args: str, host: str, port: int, console: Console, _log: list[dict[str, str]]
) -> bool:
    path = args.strip()
    if not path:
        console.print("[red]usage[/red]: /ingest <path>")
        return False
    with console.status("[dim]📂 ingesting...[/dim]", spinner="dots"):
        result = _safe_call_tool(
            console, "wiki.ingest", {"path": path}, host=host, port=port
        )
    if result is None:
        return False
    if not isinstance(result, dict):
        console.print(f"[red]unexpected response[/red]: {result!r}")
        return False
    formatters.format_ingest_result(result, console)
    return False


# Dispatch table — order here is the order shown in /help.
_SLASH_COMMANDS: dict[str, tuple[str, Any]] = {
    "/help": ("show this help", _cmd_help),
    "/quit": ("exit the REPL", _cmd_quit),
    "/exit": ("exit the REPL", _cmd_quit),
    "/clear": ("clear the screen", _cmd_clear),
    "/history": ("show this session's question history", _cmd_history),
    "/reset": ("clear the multi-turn conversation history", _cmd_reset),
    "/status": ("show daemon + wiki status", _cmd_status),
    "/search <query>": ("search the wiki (calls wiki.search)", _cmd_search),
    "/page <id>": ("read one page (calls wiki.get_page)", _cmd_page),
    "/gaps": ("list open knowledge gaps (calls wiki.find_gaps)", _cmd_gaps),
    "/report-gap <query>": (
        "record a knowledge gap (calls wiki.report_gap)",
        _cmd_report_gap,
    ),
    "/ingest <path>": ("ingest a file or directory (calls wiki.ingest)", _cmd_ingest),
}


# ---- REPL entry ----


def run(host: str, port: int, console: Console) -> None:
    """Run the interactive REPL. Returns on /quit, /exit, EOF, or
    KeyboardInterrupt.

    Multi-turn: the REPL maintains a `messages_log` of
    `{role, content}` dicts spanning the session. Each non-slash
    turn passes the log to `wiki.ask` as `prior_messages`, then
    appends the new user/assistant pair after the call returns.
    `/reset` clears the log without ending the session.
    """
    history = InMemoryHistory()
    session: PromptSession[str] = PromptSession(history=history)
    # Multi-turn conversation log. List of `{role, content}` dicts.
    # User-role entries also drive `/history`. `/reset` empties it.
    messages_log: list[dict[str, str]] = []

    _print_welcome(console)

    while True:
        try:
            line = session.prompt("> ").strip()
        except KeyboardInterrupt:
            # Ctrl-C → discard the current line and loop (parallels
            # bash / claude). Ctrl-D exits via EOFError below.
            console.print("[dim](Ctrl-D or /quit to exit)[/dim]")
            continue
        except EOFError:
            console.print("[dim]bye[/dim]")
            return

        if not line:
            continue

        if line.startswith("/"):
            should_quit = _dispatch_slash(line, host, port, console, messages_log)
            if should_quit:
                return
            continue

        # Plain text → wiki.ask with the running message history.
        arguments: dict[str, Any] = {"question": line}
        if messages_log:
            arguments["prior_messages"] = messages_log
        with console.status("[dim]🔍 thinking...[/dim]", spinner="dots"):
            result = _safe_call_tool(
                console, "wiki.ask", arguments, host=host, port=port
            )
        if result is None:
            continue
        if not isinstance(result, dict):
            console.print(f"[red]unexpected response[/red]: {result!r}")
            continue
        formatters.format_ask_result(result, console)
        console.print()  # blank line between turns

        # Append the just-completed turn to the log so the next turn
        # has it as context. We log the bare question (not the
        # excerpt-augmented one — that's the daemon's business) and
        # the assistant's answer text. Errors / invalid-citation
        # cases still get logged so the LLM sees its own prior
        # admissions of ignorance.
        if not result.get("error"):
            messages_log.append({"role": "user", "content": line})
            answer = result.get("answer")
            if isinstance(answer, str) and answer.strip():
                messages_log.append({"role": "assistant", "content": answer})


def _dispatch_slash(
    line: str,
    host: str,
    port: int,
    console: Console,
    messages_log: list[dict[str, str]],
) -> bool:
    """Parse a `/cmd args...` line and dispatch. Returns True iff the
    REPL should exit."""
    parts = line.split(maxsplit=1)
    name = parts[0]
    args = parts[1] if len(parts) > 1 else ""
    # Match against the dispatch keys, which may include placeholders
    # like `/search <query>`. Strip the placeholder for matching.
    for full_key, (_desc, handler) in _SLASH_COMMANDS.items():
        cmd_name = full_key.split(maxsplit=1)[0]
        if name == cmd_name:
            return handler(args, host, port, console, messages_log)
    console.print(
        f"[red]unknown command[/red]: {escape(name)} — try /help for the list"
    )
    return False


def _safe_call_tool(
    console: Console,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    *,
    host: str,
    port: int,
) -> Any:
    """Wrap `call_tool` with REPL-friendly error rendering — instead of
    propagating `DaemonUnreachable`, print a red message and return
    None so the loop can continue."""
    try:
        return call_tool(tool_name, arguments, host=host, port=port)
    except DaemonUnreachable as e:
        console.print(f"[red]error[/red]: {e}")
        return None


def _print_welcome(console: Console) -> None:
    console.print(
        "[bold]cogrind-workshop[/bold] interactive shell. "
        "Type a question, or [dim]/help[/dim] for slash commands. "
        "[dim]/quit[/dim] (or Ctrl-D) to exit.\n"
    )
