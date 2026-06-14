# SPDX-FileCopyrightText: 2026 Gary Frattarola <garyf@parkviewlab.ai>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for cogrind_workshop.repl.

The REPL's `run()` is an interactive `prompt_toolkit` loop — hard to
test directly. We test the individually-callable pieces: slash-command
dispatch and handlers. Each handler takes a Console + call_tool we
can mock.
"""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import patch

from rich.console import Console

from cogrind_workshop import repl

# ---- helpers ----


def _make_console() -> tuple[Console, io.StringIO]:
    """Return a Console + the underlying StringIO so tests can assert
    on rendered output."""
    buf = io.StringIO()
    return Console(file=buf, width=80, force_terminal=False, color_system=None), buf


def _ok_response(payload: Any) -> Any:
    """A canned `call_tool` return value."""
    return payload


# ---- _dispatch_slash ----


def test_dispatch_unknown_command_prints_error() -> None:
    console, buf = _make_console()
    out = repl._dispatch_slash("/nonsense", "h", 1, console, [])
    assert out is False  # don't quit
    assert "unknown command" in buf.getvalue()


def test_dispatch_quit_returns_true() -> None:
    console, _ = _make_console()
    assert repl._dispatch_slash("/quit", "h", 1, console, []) is True


def test_dispatch_exit_returns_true() -> None:
    console, _ = _make_console()
    assert repl._dispatch_slash("/exit", "h", 1, console, []) is True


def test_dispatch_help_lists_commands() -> None:
    console, buf = _make_console()
    repl._dispatch_slash("/help", "h", 1, console, [])
    out = buf.getvalue()
    # Spot-check a few commands are listed.
    for cmd in ("/help", "/quit", "/search", "/page", "/gaps", "/reset", "/ask"):
        if cmd == "/ask":
            # `/ask` isn't a registered slash command — bare text goes
            # to wiki.ask. Help mentions this in the trailer line.
            continue
        assert cmd in out


def test_dispatch_help_trailer_explains_bare_text() -> None:
    console, buf = _make_console()
    repl._dispatch_slash("/help", "h", 1, console, [])
    assert "wiki.ask" in buf.getvalue()


# ---- /history ----


def test_history_empty_shows_no_questions() -> None:
    console, buf = _make_console()
    repl._cmd_history("", "h", 1, console, [])
    assert "no questions" in buf.getvalue()


def test_history_lists_logged_questions() -> None:
    """Multi-turn message log filtered to user-role entries."""
    console, buf = _make_console()
    log = [
        {"role": "user", "content": "what is X"},
        {"role": "assistant", "content": "X is ..."},
        {"role": "user", "content": "what is Y"},
        {"role": "assistant", "content": "Y is ..."},
    ]
    repl._cmd_history("", "h", 1, console, log)
    out = buf.getvalue()
    assert "what is X" in out
    assert "what is Y" in out
    assert "1." in out and "2." in out
    # Assistant turns are NOT shown in /history (they show in transcript).
    assert "X is ..." not in out


# ---- /reset ----


def test_reset_clears_message_log_and_reports_count() -> None:
    console, buf = _make_console()
    log = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
    ]
    out = repl._cmd_reset("", "h", 1, console, log)
    assert out is False  # don't quit
    assert log == []
    assert "reset" in buf.getvalue()
    assert "2 prior turn" in buf.getvalue()  # 2 user turns


def test_reset_on_empty_log() -> None:
    console, buf = _make_console()
    log: list[dict[str, str]] = []
    repl._cmd_reset("", "h", 1, console, log)
    assert "nothing to reset" in buf.getvalue()


# ---- /search ----


def test_search_calls_wiki_search_and_renders() -> None:
    console, buf = _make_console()
    canned = {
        "query": "anything",
        "hits": [
            {
                "id": "x",
                "title": "X",
                "type": "concept",
                "score": 1.0,
                "snippet": "",
                "aliases": [],
            }
        ],
        "expansion_edges": [],
        "expanded_node_ids": [],
        "gap_detected": False,
        "truncated_expansion": False,
        "count": 1,
    }
    with patch.object(repl, "call_tool", return_value=canned) as ct:
        repl._cmd_search("anything", "h", 1, console, [])
    ct.assert_called_once()
    assert ct.call_args.args[0] == "wiki.search"
    out = buf.getvalue()
    assert "X" in out or "concept" in out


def test_search_usage_error_when_no_args() -> None:
    console, buf = _make_console()
    repl._cmd_search("", "h", 1, console, [])
    assert "usage" in buf.getvalue()


# ---- /page ----


def test_page_renders_body() -> None:
    console, buf = _make_console()
    canned = {"id": "x", "title": "X page", "body": "the body text"}
    with patch.object(repl, "call_tool", return_value=canned):
        repl._cmd_page("x", "h", 1, console, [])
    out = buf.getvalue()
    assert "X page" in out
    assert "the body text" in out


def test_page_renders_error_payload() -> None:
    console, buf = _make_console()
    canned = {"error": "not_found", "message": "no such page"}
    with patch.object(repl, "call_tool", return_value=canned):
        repl._cmd_page("nope", "h", 1, console, [])
    assert "not_found" in buf.getvalue()


def test_page_usage_error_when_no_args() -> None:
    console, buf = _make_console()
    repl._cmd_page("", "h", 1, console, [])
    assert "usage" in buf.getvalue()


# ---- /report-gap ----


def test_report_gap_shows_confirmation() -> None:
    console, buf = _make_console()
    canned = {"gap_id": "abc12345", "position": 1}
    with patch.object(repl, "call_tool", return_value=canned):
        repl._cmd_report_gap("what is X", "h", 1, console, [])
    out = buf.getvalue()
    assert "gap recorded" in out
    assert "abc12345" in out


def test_report_gap_usage_error() -> None:
    console, buf = _make_console()
    repl._cmd_report_gap("", "h", 1, console, [])
    assert "usage" in buf.getvalue()


# ---- /gaps ----


def test_gaps_renders_list() -> None:
    console, buf = _make_console()
    canned = {
        "gaps": [
            {"id": "abc12345", "query": "what is foo", "created_at": "2026-05-18T00:00:00Z"}
        ]
    }
    with patch.object(repl, "call_tool", return_value=canned):
        repl._cmd_gaps("", "h", 1, console, [])
    assert "abc12345" in buf.getvalue()


# ---- /status ----


def test_status_renders_table() -> None:
    console, buf = _make_console()
    canned = {
        "version": "0.1.0",
        "milestone": "M2.7",
        "wiki_exists": True,
        "pages_indexed": 10,
        "embedding": {"provider": "fastembed", "model": "x", "dim": 384},
        "daemon": {"uptime_seconds": 12.0},
        "corpus_mutex": {},
        "tasks": {},
    }
    with patch.object(repl, "call_tool", return_value=canned):
        repl._cmd_status("", "h", 1, console, [])
    out = buf.getvalue()
    assert "0.1.0" in out


# ---- /clear ----


def test_clear_returns_false() -> None:
    console, _ = _make_console()
    # Just verify the handler doesn't raise and signals "keep looping."
    out = repl._cmd_clear("", "h", 1, console, [])
    assert out is False


# ---- daemon unreachable ----


def test_safe_call_tool_returns_none_on_daemon_unreachable() -> None:
    """The REPL wraps call_tool in `_safe_call_tool` so DaemonUnreachable
    becomes a printed error + None return (loop continues instead of
    crashing out)."""
    console, buf = _make_console()
    with patch.object(
        repl, "call_tool", side_effect=repl.DaemonUnreachable("cobalt-grinding down")
    ):
        out = repl._safe_call_tool(console, "wiki.status", host="h", port=1)
    assert out is None
    assert "cobalt-grinding down" in buf.getvalue()


# ---- /ingest ----


def test_ingest_calls_wiki_ingest() -> None:
    console, buf = _make_console()
    canned = {
        "source_id": "file-x__1",
        "page_path": "pages/sources/file-x__1.md",
        "location_uri": "file:/tmp/x",
        "location_kind": "file",
        "files_ingested": 1,
        "pages_written": ["file-x__1"],
        "entity_pages_written": [],
        "glossary_pages_written": [],
        "section_pages_written": [],
        "files_ignored": [],
        "links_added": 0,
        "skipped": False,
    }
    with patch.object(repl, "call_tool", return_value=canned) as ct:
        repl._cmd_ingest("/tmp/x", "h", 1, console, [])
    ct.assert_called_once()
    assert ct.call_args.args[0] == "wiki.ingest"
    assert "file-x" in buf.getvalue()


def test_ingest_usage_error() -> None:
    console, buf = _make_console()
    repl._cmd_ingest("", "h", 1, console, [])
    assert "usage" in buf.getvalue()


# ---- main.py --chat flag wiring ----


def test_main_chat_flag_invokes_repl_run() -> None:
    """`cogrind-workshop --chat` should call `repl.run()`. Mock the
    run function so this test doesn't actually open an interactive
    session."""
    from click.testing import CliRunner

    from cogrind_workshop import main

    runner = CliRunner()
    with patch("cogrind_workshop.repl.run") as fake_run:
        result = runner.invoke(main.main, ["--chat"])
    assert result.exit_code == 0
    fake_run.assert_called_once()
