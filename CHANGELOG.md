# Changelog

All notable changes to this project are recorded here. Each release entry has two parts: a **Highlights** paragraph, generated at release time by an Anthropic-API call, and the **categorized changes**, the pull requests merged since the previous tag grouped by their [Conventional Commit](https://www.conventionalcommits.org/) type, with any commit that reached the release without a pull request listed under Direct commits. Both are written by dev-tools' `generate-changelog`, which the release workflow runs at a pinned release. The v0.1.0 entry below, written by an earlier generator, carries the Highlights paragraph alone and stays as published.

The release workflow on every tag push regenerates both, commits the new
section here, and uses the same content as the GitHub Release body.

<!--
  Keep-a-Changelog ordering: [Unreleased] at the top, then newest
  released version, then older versions. generate-changelog inserts
  new "## [vX.Y.Z] - YYYY-MM-DD" sections directly below [Unreleased].
  Don't remove the marker.
-->

## [Unreleased]

## [v0.1.3] - 2026-09-30

### Highlights

This release pins `mcp[cli]` below 2.0, fixing a break in which a fresh install of the previous version resolved mcp 2.2.0 and every CLI command and REPL turn failed with `ValueError: not enough values to unpack (expected 3, got 2)` before connecting to the server. The remaining work is internal: CI now runs the standard fast test tier, and the agent pointer files and contributor docs were aligned with handbook v2.1.0.

### Bug fixes

- Keep mcp below 2 (#10)

### Maintenance

- Align with handbook v2.1.0 (#9)

## [v0.1.2] - 2026-09-27

### Highlights

This release is internal maintenance: the repository moves from squash merges and a direct back-merge to merge commits and a back-merge pull request, with the release workflows re-assembled from the handbook templates and their dev-tools pins updated. The only change a reader will notice is in the contributing guide, which now describes the merge-commit and closing back-merge pull request flow.

### Maintenance

- Merge commits and the checked back-merge pull request (#7)

## [v0.1.1] - 2026-09-27

### Highlights

This release is mostly documentation and release-infrastructure work: the README and contributing guide are corrected to describe the CLI as it actually behaves — a single command driven by flags (`--ingest`, `--ask`, `--query`, `--status`, `--chat`) rather than subcommands, with no `--search` — and the in-code notes now reflect that the REPL carries prior turns and offers `/exit` and `/reset`. The release procedure is replaced by a link to the handbook's "Cutting a release", and the changelog description is updated for the shared generator, under which `chore:`, `ci:`, `build:` and `style:` entries appear under Maintenance and unrecognised titles under Other changes. The remaining changes rebuild the release and dev-release workflows from the handbook's parts, adding gate checks that reject tags carrying a dev marker or not greater than the previous release; publishing configuration is unchanged.

### Docs

- Correct the README, CONTRIBUTING and changelog header before the release (#6)

### Maintenance

- Drop the shallow re-fetch from the version guard (#3)
- Assemble the release workflows from the handbook's parts (#4)
- Generate the changelog with dev-tools' shared script (#5)

## [v0.1.0] - 2026-07-01

### Highlights

Initial release of cogrind-workshop, a human-facing MCP client for a running cobalt-grinding daemon, providing one-shot `ingest`, `ask`, and `search` subcommands alongside an interactive chat REPL. Distributed under AGPL-3.0-or-later with a commercial option documented in LICENSING.md.

