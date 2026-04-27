# WeftMark

A multi-user web platform for managing weaving projects — from design upload and preview through loom-side step tracking, yarn inventory, and project reporting.

> **This project was designed and built with [Claude AI](https://claude.ai) (Anthropic).** The requirements, architecture decisions, and implementation were developed collaboratively through conversation with Claude. Project memory and decision rationale are preserved in `.claude/memory/` and `docs/requirements/` so future sessions can pick up with full context.

---

## What It Does

- **Upload WIF files** — import weaving drafts from software like TempoWeave, Fiberworks PCW, WeavIt, and others. Files are linted against the WIF 1.1 standard with detailed warnings.
- **Preview designs** — render drawdown, threading diagram, and tie-up views using PyWeaving. Zoom, pan, color simulation, and repeat views included.
- **Track weaving at the loom** — step-by-step pick tracking with lift-tracking (lever looms) and treadle-tracking (floor looms) activity types. Designed for tablet and mobile use at the loom.
- **Manage equipment** — document your looms with versioned state history to track upgrades over time.
- **Manage yarn inventory** — track individual skeins with unique IDs, estimate consumption from WIF data, and deduct inventory as projects progress.
- **Generate reports** — warping plans, tie-up sheets, session logs, and full activity reports exportable as PDF.
- **Share selectively** — projects are private by default; share via revocable slug URLs with no account required for viewers.

---

## Tech Stack

| Layer | Technology |
| --- | --- |
| Frontend | React, Vite, TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, React Router |
| Backend | FastAPI (Python), SQLAlchemy, Alembic |
| Database | PostgreSQL |
| Task Queue | Celery + Redis |
| Rendering | PyWeaving |
| Authentication | Authentik (OIDC) — any OIDC-compliant provider supported |
| Deployment | Docker + Docker Compose |

---

## Repository Structure

```text
weaving_site/
├── .claude/
│   └── memory/             # Project memory for Claude AI sessions
│       ├── MEMORY.md       # Memory index
│       ├── project.md      # Platform decisions and architecture
│       └── feedback.md     # Collaboration preferences
├── docs/
│   ├── requirements/       # Full feature requirements
│   │   ├── README.md       # Requirements index
│   │   ├── overview.md
│   │   ├── wif-import.md
│   │   ├── design-preview.md
│   │   ├── activities.md
│   │   ├── equipment-inventory.md
│   │   ├── yarn-inventory.md
│   │   ├── reports.md
│   │   ├── sharing-profiles.md
│   │   ├── admin.md
│   │   └── phase2.md
│   ├── samples/            # Sample WIF files for development
│   └── standard/           # WIF 1.1 specification
├── frontend/               # React application (Vite)
├── backend/                # FastAPI application
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Getting Started

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- An OIDC provider (Authentik recommended for local development)

### Setup

```bash
# Clone the repository
git clone <repo-url>
cd weaving_site

# Copy environment config
cp .env.example .env
# Edit .env with your configuration

# Start all services
docker compose up
```

The frontend will be available at `http://localhost:3000` and the API at `http://localhost:8000`.

### Development

```bash
# Backend (FastAPI)
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend (React)
cd frontend
npm install
npm run dev
```

---

## Documentation

- **Project Status:** [`STATUS.md`](STATUS.md) — what's built, what's in progress, what's next
- **Requirements:** [`docs/requirements/`](docs/requirements/README.md)
- **WIF Standard:** [`docs/standard/standard-wif1-1.txt`](docs/standard/standard-wif1-1.txt)
- **Project Memory:** [`.claude/memory/`](.claude/memory/MEMORY.md)

---

## License

This project is licensed under the **PolyForm Noncommercial License 1.0.0**. You may use, modify, and distribute this software for any noncommercial purpose. Commercial use is not permitted without explicit written permission from the author.

See [LICENSE](LICENSE) for the full terms.

---

## Built With Claude

This project was conceived, designed, and built in collaboration with **Claude** by [Anthropic](https://anthropic.com). Requirements were gathered through structured conversation, architectural decisions were made collaboratively, and all documentation reflects those discussions.

If you are a Claude session picking up this project: read [`.claude/memory/MEMORY.md`](.claude/memory/MEMORY.md) first, then the relevant requirements documents before making any changes.
