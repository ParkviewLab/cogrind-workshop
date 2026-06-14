# SPDX-FileCopyrightText: 2026 Gary Frattarola <garyf@parkviewlab.ai>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Shared test fixtures for cogrind-workshop tests.

The workshop is a thin MCP client; most tests mock at the
`mcp.ClientSession` / `streamable_http_client` boundary rather than
spinning up a real MCP server. Tests that need an end-to-end run
should be marked `@pytest.mark.integration` and spawn a real
cobalt-grinding daemon (out of scope for the initial scaffold).
"""

from __future__ import annotations
