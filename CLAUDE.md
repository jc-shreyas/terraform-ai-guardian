# CLAUDE.md — Project Context for Claude Code

## Project Overview

AI-powered DevOps agents that review Terraform PRs for security/compliance issues and debug CI/CD pipeline failures.

## Tech Stack

- **Python 3.11+**
- **Anthropic Claude API** (via the `anthropic` Python SDK) — no LangGraph, no LangChain
- **PyGithub** — GitHub API interaction

## Agent Architecture

Both agents are **plain Python scripts**. There is no graph framework. Each agent:
1. Instantiates a state dataclass (`PRReviewState` / `CICDDebugState`)
2. Calls a series of Python functions (steps) that read and mutate the state
3. Uses the Anthropic SDK directly for all LLM calls

## Key Directories

| Path | Purpose |
|------|---------|
| `agent-pr-reviewer/` | Terraform PR review agent |
| `agent-cicd-debugger/` | GitHub Actions failure debugger |
| `shared/` | Shared config and prompt templates |
| `infra/` | Sample Terraform with intentional security issues |
| `tests/` | Test suite |

## Important Conventions

- **No LangGraph** — do not introduce it; state is passed as plain dataclasses
- **No TypedDict for agent state** — use `@dataclass` from the standard library
- Agents call `anthropic.Anthropic().messages.create(...)` directly
- GitHub interaction goes through `PyGithub` (`github.Github`)
