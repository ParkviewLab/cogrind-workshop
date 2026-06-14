# SPDX-FileCopyrightText: 2026 Gary Frattarola <garyf@parkviewlab.ai>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""cogrind-workshop — human-facing MCP client for a `cobalt-grinding` server.

Equivalent in role to Claude Desktop or Claude Code: one MCP client
among many that can drive a running `cobalt-grinding` daemon. No
business logic; pure transport + rendering.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__: str = version("cogrind-workshop")
except PackageNotFoundError:  # editable install before first build
    __version__ = "0.0.0+local"
