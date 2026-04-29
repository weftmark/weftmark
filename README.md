# WeftMark

A web platform for handweavers to manage projects from design upload through loom-side step tracking.

> **Built with [Claude AI](https://claude.ai) (Anthropic).** Requirements, architecture decisions, and implementation were developed collaboratively through conversation with Claude.

---

## What It Does

- **Upload WIF files** — import weaving drafts from software like TempoWeave, Fiberworks PCW, WeavIt, and others. Files are validated against the WIF 1.1 standard.
- **Preview designs** — render drawdown, threading diagram, and tie-up views. Zoom, pan, colour simulation, and repeat views included.
- **Track weaving at the loom** — step-by-step pick tracking with lift-tracking (lever looms) and treadle-tracking (floor looms) activity types.
- **Manage equipment** — document your looms and track configuration changes over time.

---

## Tech Stack

| Layer | Technology |
| --- | --- |
| Frontend | React 18, Vite, TypeScript, Tailwind CSS, TanStack Query, React Router |
| Backend | FastAPI (Python), SQLAlchemy, Alembic |
| Database | PostgreSQL |
| Authentication | [Clerk](https://clerk.com) |
| Deployment | Docker + Docker Compose |

---

## Repository Structure

```text
weftmark/
├── backend/                # FastAPI application
│   ├── app/                # Routes, models, services
│   ├── alembic/            # Database migrations
│   └── tests/              # pytest test suite
├── frontend/               # React application (Vite)
│   └── src/
├── docs/
│   ├── requirements/       # Feature requirements
│   └── standard/           # WIF 1.1 specification
├── docker-compose.yml
└── .env.example            # Required environment variables (copy to .env)
```

---

## Getting Started

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- A [Clerk](https://clerk.com) account (free tier is sufficient for local development)

### Setup

```bash
# Clone the repository
git clone https://github.com/weftmark/weftmark.git
cd weftmark

# Copy environment config and fill in values
cp .env.example .env

# Start all services
docker compose up
```

The frontend will be available at `http://localhost:3000` and the API at `http://localhost:8000`.

See `.env.example` for all required environment variables and where to obtain them.

> **Note — Clerk key is baked into the frontend image at build time.**
> `VITE_CLERK_PUBLISHABLE_KEY` is compiled into the static JS bundle by Vite during `docker compose build`. This means the container cannot be reused across Clerk instances (e.g. dev vs prod) without a rebuild, and self-hosted deployments using a different Clerk account must build their own image.
> Runtime configurability is tracked in [#87](https://github.com/weftmark/weftmark/issues/87) and will be addressed in a future release.

### Local Development (without Docker)

```bash
# Backend (FastAPI)
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
uvicorn app.main:app --reload

# Frontend (React)
cd frontend
npm install
npm run dev
```

---

## Running Tests

```bash
# Backend
cd backend
pytest

# Frontend type check
cd frontend
npx tsc -b --noEmit
```

---

## Documentation

- **Requirements:** [`docs/requirements/`](docs/requirements/)
- **WIF Standard:** [`docs/standard/standard-wif1-1.txt`](docs/standard/standard-wif1-1.txt)

---

## License

Source-available under the **Business Source License 1.1 (BUSL-1.1)**. The source code is publicly visible for review and learning. Commercial use is not permitted. See [LICENSE](LICENSE) for full terms.
