# Contributing to WeftMark

Thank you for your interest in contributing. This document covers how to get involved, what to expect, and how to keep the project consistent.

## This Project Was Built With Claude AI

The requirements, architecture, and implementation of this project were developed collaboratively using [Claude](https://claude.ai) by Anthropic. If you are continuing work with Claude, read [`.claude/memory/MEMORY.md`](.claude/memory/MEMORY.md) at the start of any session.

## License

This project is licensed under the [Business Source License 1.1 (BUSL-1.1)](LICENSE). The source is publicly visible for review and learning. Commercial use is not permitted until 2029-01-01, at which point the license converts to MIT. By submitting a contribution you agree that your work will be licensed under the same terms.

## Getting Started

1. Read the [requirements documentation](docs/requirements/README.md) to understand the full scope of the project before making changes.
2. Read [`docs/architecture.md`](docs/architecture.md) for the tech stack, repo structure, and local setup instructions.
3. If working with Claude, read [`.claude/memory/MEMORY.md`](.claude/memory/MEMORY.md) at the start of any session.

## Development Workflow

- **Branch** from `dev` for all changes — never commit directly to `main` or `dev`.
- **Pull requests target `dev`** — not `main`. The `main` branch is prod-ready; merges to it go through `dev` first.
- **Hotfixes** branch from `main`, PR to `main`, then backport to `dev` as a follow-up PR.
- **Keep commits focused** — one logical change per commit.
- **Write meaningful commit messages** — describe why, not just what.
- **Do not break existing behavior** without discussion.

## Code Style

### Backend (Python / FastAPI)

- Follow [PEP 8](https://peps.python.org/pep-0008/)
- Use type hints throughout
- Validate data at API boundaries using Pydantic models
- Keep business logic out of route handlers

### Frontend (TypeScript / React)

- Use TypeScript strictly — avoid `any`
- Prefer functional components and hooks
- Keep components small and single-purpose
- Use TanStack Query for all server state

### General

- No commented-out code
- No debug print/console.log statements committed
- Environment-specific values belong in `.env`, never in source

## Reporting Issues

Open an issue describing:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Environment details (OS, browser, Docker version)

## Suggesting Features

Before implementing a feature, open an issue to discuss it. Check [`docs/requirements/phase2.md`](docs/requirements/phase2.md) to see if it is already on the roadmap.
