# SPDX-FileCopyrightText: 2026 Gary Frattarola <garyf@parkviewlab.ai>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Smoke tests for the cogrind-workshop CLI + client surface.

These don't run against a real daemon — they catch import-graph
regressions and basic CLI-registration breakage. Integration tests
against a running cobalt-grinding daemon are deferred (marked
`@pytest.mark.integration` when added).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from cogrind_workshop import __version__, client, main


def test_package_imports():
    """The package's public modules import without error."""
    # Touch each module to catch ImportError regressions.
    assert __version__  # defined (string)
    assert hasattr(client, "call_tool")
    assert hasattr(client, "stream_task")
    assert hasattr(client, "DaemonUnreachable")
    assert callable(main.main)


def test_cli_help_runs():
    """`cogrind-workshop --help` returns 0 and lists the documented flags."""
    runner = CliRunner()
    result = runner.invoke(main.main, ["--help"])
    assert result.exit_code == 0
    out = result.output
    # Spot-check a few of the documented flags — both legacy and the
    # M3/M4/M5 additions.
    expected_flags = (
        "--host",
        "--port",
        "--status",
        "--index",
        "--index-full",
        "--task-list",
        "--ingest",
        "--query",
        "--ask",
        "--find-gaps",
        "--report-gap",
        "--chat",
        "--top-k",
        "--expand-hops",
    )
    for flag in expected_flags:
        assert flag in out, f"--help is missing {flag}; got:\n{out}"


def test_cli_no_flags_exits_with_hint():
    """Bare `cogrind-workshop` (no flags) prints a hint and exits 2."""
    runner = CliRunner()
    result = runner.invoke(main.main, [])
    assert result.exit_code == 2
    assert "No action specified" in result.output


def test_cli_multiple_flags_rejected():
    """Passing two action flags at once errors with a clear message."""
    runner = CliRunner()
    result = runner.invoke(main.main, ["--status", "--index"])
    assert result.exit_code == 2
    assert "exactly one action flag" in result.output


def test_cli_version_flag():
    """`--version` reports the package version."""
    runner = CliRunner()
    result = runner.invoke(main.main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_call_tool_decodes_json_text_block():
    """`call_tool` JSON-decodes the first text content block of the
    MCP call_tool result. Mocked at the ClientSession boundary so we
    don't need a real server."""
    payload = {"ok": True, "value": 42}

    # Build a fake MCP result with one TextContent block holding JSON.
    text_block = MagicMock()
    text_block.text = json.dumps(payload)
    fake_result = MagicMock()
    fake_result.content = [text_block]

    # Patch streamable_http_client + ClientSession so call_tool() never
    # opens a real HTTP connection.
    fake_session = AsyncMock()
    fake_session.initialize = AsyncMock()
    fake_session.call_tool = AsyncMock(return_value=fake_result)
    # ClientSession used as async-context-manager
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=None)

    fake_streams = (MagicMock(), MagicMock(), MagicMock())

    fake_http_cm = AsyncMock()
    fake_http_cm.__aenter__ = AsyncMock(return_value=fake_streams)
    fake_http_cm.__aexit__ = AsyncMock(return_value=None)

    with (
        patch.object(client, "streamable_http_client", return_value=fake_http_cm),
        patch.object(client, "ClientSession", return_value=fake_session),
    ):
        result = client.call_tool("wiki.status", host="127.0.0.1", port=7474)

    assert result == payload
    fake_session.call_tool.assert_awaited_once_with("wiki.status", {})


def test_call_tool_returns_raw_text_when_not_json():
    """If the content block isn't valid JSON, return it as a plain string."""
    text_block = MagicMock()
    text_block.text = "not-json"
    fake_result = MagicMock()
    fake_result.content = [text_block]

    fake_session = AsyncMock()
    fake_session.initialize = AsyncMock()
    fake_session.call_tool = AsyncMock(return_value=fake_result)
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=None)

    fake_streams = (MagicMock(), MagicMock(), MagicMock())
    fake_http_cm = AsyncMock()
    fake_http_cm.__aenter__ = AsyncMock(return_value=fake_streams)
    fake_http_cm.__aexit__ = AsyncMock(return_value=None)

    with (
        patch.object(client, "streamable_http_client", return_value=fake_http_cm),
        patch.object(client, "ClientSession", return_value=fake_session),
    ):
        result = client.call_tool("noop", host="127.0.0.1", port=7474)

    assert result == "not-json"


# ---- new flag handlers (M3/M4/M5) ----


def test_cli_ingest_calls_wiki_ingest(tmp_path):
    """`--ingest <path>` calls `wiki.ingest` and renders the response."""
    runner = CliRunner()
    f = tmp_path / "hello.md"
    f.write_text("# Hello", encoding="utf-8")

    canned_response = {
        "source_id": "file-hello-md__abc",
        "page_path": "pages/sources/file-hello-md__abc.md",
        "location_uri": f"file:{f}",
        "location_kind": "file",
        "content_hash": "a" * 64,
        "files_ingested": 1,
        "pages_written": ["file-hello-md__abc"],
        "entity_pages_written": [],
        "glossary_pages_written": [],
        "section_pages_written": [],
        "files_ignored": [],
        "links_added": 0,
        "started_at": "2026-05-18T00:00:00Z",
        "finished_at": "2026-05-18T00:00:01Z",
        "skipped": False,
    }

    with patch.object(main, "call_tool", return_value=canned_response) as ct:
        result = runner.invoke(main.main, ["--ingest", str(f)])

    assert result.exit_code == 0, result.output
    ct.assert_called_once()
    # First positional arg is the tool name; second is the kwargs dict.
    args, kwargs = ct.call_args
    assert args[0] == "wiki.ingest"
    # Either path comes as 2nd positional arg (dict) or as named kwarg.
    payload = args[1] if len(args) > 1 else kwargs.get("arguments", {})
    assert payload == {"path": str(f)}
    # The pretty-printed table mentions the source id.
    assert "file-hello-md" in result.output


def test_cli_query_calls_wiki_search():
    runner = CliRunner()
    canned = {
        "query": "anthropic",
        "hits": [
            {
                "id": "org-anthropic__1",
                "title": "Anthropic",
                "type": "entity",
                "score": 1.5,
                "snippet": "...",
                "aliases": [],
            }
        ],
        "expansion_edges": [],
        "expanded_node_ids": [],
        "gap_detected": False,
        "truncated_expansion": False,
        "count": 1,
    }
    with patch.object(main, "call_tool", return_value=canned) as ct:
        result = runner.invoke(main.main, ["--query", "anthropic"])

    assert result.exit_code == 0, result.output
    ct.assert_called_once()
    assert ct.call_args.args[0] == "wiki.search"
    args = ct.call_args.args[1]
    assert args["query"] == "anthropic"
    # Output mentions the hit's title.
    assert "Anthropic" in result.output


def test_cli_query_passes_top_k_and_expand_hops():
    runner = CliRunner()
    canned = {"query": "x", "hits": [], "expansion_edges": [], "expanded_node_ids": [], "gap_detected": True, "truncated_expansion": False, "count": 0}
    with patch.object(main, "call_tool", return_value=canned) as ct:
        runner.invoke(main.main, ["--query", "x", "--top-k", "20", "--expand-hops", "2"])
    args = ct.call_args.args[1]
    assert args["top_k"] == 20
    assert args["expand_hops"] == 2


def test_cli_query_renders_gap_when_no_hits():
    runner = CliRunner()
    canned = {"query": "nothing-matches", "hits": [], "expansion_edges": [], "expanded_node_ids": [], "gap_detected": True, "truncated_expansion": False, "count": 0}
    with patch.object(main, "call_tool", return_value=canned):
        result = runner.invoke(main.main, ["--query", "nothing-matches"])
    assert result.exit_code == 0
    assert "no hits" in result.output
    assert "gap_detected" in result.output


def test_cli_ask_calls_wiki_ask_and_renders_citations():
    runner = CliRunner()
    canned = {
        "question": "What is MCP?",
        "answer": "MCP is the Model Context Protocol [page:concept-mcp__1].",
        "citations": [{"page_id": "concept-mcp__1", "valid": True}],
        "invalid_citations": [],
        "hits_used": [
            {"id": "concept-mcp__1", "title": "MCP", "type": "concept", "score": 1.0, "snippet": "", "aliases": []}
        ],
        "gap_detected": False,
        "truncated_context": False,
    }
    with patch.object(main, "call_tool", return_value=canned) as ct:
        result = runner.invoke(main.main, ["--ask", "What is MCP?"])
    assert result.exit_code == 0, result.output
    ct.assert_called_once()
    assert ct.call_args.args[0] == "wiki.ask"
    assert ct.call_args.args[1]["question"] == "What is MCP?"
    assert "Model Context Protocol" in result.output
    assert "concept-mcp__1" in result.output


def test_cli_ask_flags_invalid_citations_in_output():
    runner = CliRunner()
    canned = {
        "question": "anything",
        "answer": "Foo [page:made-up__x]",
        "citations": [{"page_id": "made-up__x", "valid": False}],
        "invalid_citations": ["made-up__x"],
        "hits_used": [],
        "gap_detected": True,
        "truncated_context": False,
    }
    with patch.object(main, "call_tool", return_value=canned):
        result = runner.invoke(main.main, ["--ask", "anything"])
    assert result.exit_code == 0
    assert "hallucination" in result.output
    assert "made-up__x" in result.output
    assert "gap_detected" in result.output


def test_cli_find_gaps_lists_gaps():
    runner = CliRunner()
    canned = {
        "gaps": [
            {"id": "abc12345", "query": "what is foo", "created_at": "2026-05-18T00:00:00Z", "why": "user asked"},
        ]
    }
    with patch.object(main, "call_tool", return_value=canned) as ct:
        result = runner.invoke(main.main, ["--find-gaps"])
    assert result.exit_code == 0
    ct.assert_called_once()
    assert ct.call_args.args[0] == "wiki.find_gaps"
    assert "abc12345" in result.output


def test_cli_find_gaps_handles_empty_list():
    runner = CliRunner()
    with patch.object(main, "call_tool", return_value={"gaps": []}):
        result = runner.invoke(main.main, ["--find-gaps"])
    assert result.exit_code == 0
    assert "no open gaps" in result.output


def test_cli_report_gap_calls_wiki_report_gap():
    runner = CliRunner()
    canned = {"gap_id": "deadbeef", "position": 1}
    with patch.object(main, "call_tool", return_value=canned) as ct:
        result = runner.invoke(main.main, ["--report-gap", "an unanswered question"])
    assert result.exit_code == 0
    ct.assert_called_once()
    assert ct.call_args.args[0] == "wiki.report_gap"
    assert ct.call_args.args[1]["query"] == "an unanswered question"
    assert "deadbeef" in result.output


def test_cli_rejects_mixing_new_flags_with_old():
    """The 'exactly one action' guard covers the new flags too."""
    runner = CliRunner()
    result = runner.invoke(main.main, ["--status", "--query", "anything"])
    assert result.exit_code == 2
    assert "exactly one action flag" in result.output


def test_cli_help_lists_at_least_one_m3_m4_m5_flag():
    """Sanity check: the human-facing --help text mentions the new
    cognitive-skill flags. (Belt-and-suspenders on top of
    `test_cli_help_runs`'s per-flag checks.)"""
    runner = CliRunner()
    result = runner.invoke(main.main, ["--help"])
    assert result.exit_code == 0
    # At least one each from M3 / M4 / M5.
    assert "--ingest" in result.output  # M3
    assert "--query" in result.output  # M4
    assert "--ask" in result.output  # M5


def test_daemon_unreachable_raised_on_connect_error():
    """`DaemonUnreachable` is raised when the underlying transport
    can't reach the daemon. We simulate a `ConnectError` from httpx."""
    import httpx

    fake_http_cm = AsyncMock()
    fake_http_cm.__aenter__ = AsyncMock(side_effect=httpx.ConnectError("nope"))
    fake_http_cm.__aexit__ = AsyncMock(return_value=None)

    with (
        patch.object(client, "streamable_http_client", return_value=fake_http_cm),
        pytest.raises(client.DaemonUnreachable, match="could not reach cobalt-grinding"),
    ):
        client.call_tool("wiki.status", host="127.0.0.1", port=9999)
