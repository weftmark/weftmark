# Contributing to WeftMark

Thank you for your interest in contributing. This document covers how to get involved, what to expect, and how to keep the project consistent.

## This Project Was Built With Claude AI

The requirements, architecture, and implementation of this project were developed collaboratively using [Claude](https://claude.ai) by Anthropic. If you are continuing work with Claude, read [`.claude/memory/MEMORY.md`](.claude/memory/MEMORY.md) at the start of any session.

## License

This project is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE). Contributions are accepted under the same terms. By submitting a contribution you agree that your work will be licensed accordingly.

Commercial use of this software or any derivative work requires explicit written permission from the project author.

## Getting Started

1. Read the [requirements documentation](docs/requirements/README.md) to understand the full scope of the project before making changes.
2. Review the [project memory](.claude/memory/project.md) for key architectural decisions and the rationale behind them.
3. Set up your local environment using the [README](README.md#getting-started) instructions.

## Development Workflow

- **Branch** from `main` for all changes.
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
