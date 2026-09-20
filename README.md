# cogrind-workshop

Human-facing MCP client for a running [`cobalt-grinding`](https://github.com/ParkviewLab/cobalt-grinding) daemon. One-shot subcommands (`ingest`, `ask`, `search`) and an interactive REPL (`chat`). Equivalent in role to Claude Desktop or Claude Code — just one MCP client among many; no privileged side-door into the cognitive system.

## Status

**Implemented.** One-shot flags (`--ingest`, `--ask`, `--search`, `--status`, …) and an interactive REPL (`--chat`, with slash commands) drive a running `cobalt-grinding` daemon over MCP. Originally **Track C of M2.7** in the CoGrind plan — see [`cobalt-grinding/docs/plan.md`](https://github.com/ParkviewLab/cobalt-grinding/blob/main/docs/plan.md) for the full design.

## Releasing

Tag-driven via the release workflow on push of a `v*` tag. Use the [`ParkviewLab/dev-tools`](https://github.com/ParkviewLab/dev-tools) helpers — they enforce the SSOT-tag-CI loop (`pyproject.toml` is the only place the version lives; CI verifies the pushed tag matches before publishing).

```sh
git bump patch              # 0.1.5 → 0.1.6, committed
git release                 # annotated tag v0.1.6 from pyproject.toml
git push --follow-tags      # CI fires
```

Don't have the helpers? Install once: `git clone https://github.com/ParkviewLab/dev-tools.git ~/dev-tools && cd ~/dev-tools && ./install.sh`.

The workflow runs three jobs: a **gate** (tag matches `pyproject.toml`; tag reachable from `origin/main`) gates the **pypi** publish (wheel + sdist via trusted publishing — no Docker image, since this is a CLI client, not a server). After the publish, a **changelog** job generates the new `CHANGELOG.md` section (LLM-written "Highlights" paragraph + a [`git-cliff`](https://git-cliff.org/) categorized commit list), commits it back to `main`, and creates the GitHub Release with the same content as its body.

### Commit message convention

The changelog job categorizes commits using [Conventional Commits](https://www.conventionalcommits.org/) prefixes (the full list is in the ParkviewLab handbook's `commits-and-changelogs.md`):

| Prefix | Section | Notes |
|---|---|---|
| `feat:` | Features | user-visible |
| `fix:` | Bug fixes | user-visible |
| `perf:` | Performance | user-visible |
| `refactor:` | Refactor | |
| `docs:` | Docs | |
| `test:` | Tests | |
| `chore:` / `ci:` / `build:` / `style:` | _(dropped)_ | not surfaced in CHANGELOG |

Squash-merge PRs use the PR title as the commit subject — so the **PR title** is what needs the prefix. Commits without a recognised prefix are silently dropped from the CHANGELOG (still in git history). The "Highlights" paragraph requires the `ANTHROPIC_API_KEY` org-level secret; if the LLM call fails, a placeholder lands and the release still ships.

## License

cogrind-workshop is **dual-licensed**. By default it is free software under the **GNU Affero General Public License v3.0 or later** (`AGPL-3.0-or-later`); see [`LICENSE`](LICENSE) for the full text. A separate **commercial license** is available from the copyright holder for use that cannot comply with the AGPL (e.g. embedding in a closed-source product). See [`LICENSING.md`](LICENSING.md) for details.

Copyright © 2026 Gary Frattarola.
