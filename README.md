# WeftMark

[![codecov](https://codecov.io/gh/weftmark/weftmark/graph/badge.svg?token=GRAPH_TOKEN)](https://codecov.io/gh/weftmark/weftmark)

**Weaving project management — from design file to finished cloth.**

WeftMark is a web platform for handweavers. Upload your WIF drafts, track picks at the loom, manage your equipment and yarn, and document your work from warp to finishing.

---

> **Built with Claude AI**
>
> The requirements, architecture, and implementation of WeftMark were developed collaboratively with [Claude](https://claude.ai) by Anthropic. Claude wrote the majority of the code in this repository through an iterative conversation-driven process. This is disclosed prominently because we believe AI development transparency matters.
>
> If you are continuing development with Claude, start by reading [`CLAUDE.md`](CLAUDE.md) and [`.claude/memory/MEMORY.md`](.claude/memory/MEMORY.md).

---

## Features

### At the loom

Pick-by-pick tracking for both **treadle-tracking** (floor loom) and **lift-tracking** (lever/shaft loom) projects. The interface is built for tablets and phones in portrait orientation — large tap targets, keyboard shortcuts, and Bluetooth pedal support out of the box.

- Step forward and back through picks with buttons, arrow keys, or a foot pedal
- Visual treadle or shaft display for the current pick
- Drawdown canvas that scrolls with your position so you always see where you are
- Weft color strip for designs with color-coded picks
- Multi-item projects — track a full run of towels or napkins on one warp

### Before you weave

- **Project landing page** — review your design, set color replacements, and configure warp setup before tracking starts
- **Color palette editor** — swap warp and weft colors per-project to preview colorways without touching the source file. Colors flow through the drawdown, pick display, and completed summary automatically
- **Design preview** — full draft layout (threading diagram, tie-up, drawdown) rendered server-side with your project colors applied

### Draft library

- Upload WIF files from any weaving software (TempoWeave, Fiberworks, WeavIt, and others)
- WIF 1.1 validation with a detailed linting report on import
- Draft detail page with threading, tie-up, drawdown, color palette, EPI, warp/weft measurements, and reed recommendations
- Draft drawdown preview with pan and zoom

### Equipment inventory

- Document your looms with full specifications
- **Versioned loom history** — track upgrades over time; projects reference the exact loom configuration they were woven on
- **Reed inventory** — record which reeds you own; get recommendations based on draft EPI

### Yarn inventory

- Track yarn by product (brand, fiber, weight, color) and by individual physical unit (skeins, cones, tubes)

### When you're done

- Project completion summary with design preview, session metrics, and warp setup details
- Photo documentation — attach photos at any point; photos appear in the completed summary
- Notes field for observations about the draft, loom behavior, or finished cloth

### Platform

- Private by default — your drafts and projects are yours alone
- Invite-only registration with admin approval
- Light and dark mode, metric and imperial measurement support
- Admin console for user management, platform health, and observability

---

## Getting Started

See [docs/architecture.md](docs/architecture.md) for the full technical overview, or jump straight to setup:

```bash
git clone https://github.com/weftmark/weftmark.git
cd weftmark
cp .env.example .env   # fill in Clerk keys and database URL
docker compose up
```

App at `http://localhost:3000` · API at `http://localhost:8000`

For detailed setup, environment variables, and local development without Docker, see:

- [backend/README.md](backend/README.md)
- [frontend/README.md](frontend/README.md)

---

## Documentation

| Document | Description |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | Tech stack, repo structure, deployment, API security |
| [docs/requirements/](docs/requirements/) | Full feature requirements |
| [docs/design-system.md](docs/design-system.md) | UI palette, tokens, and component conventions |
| [docs/testing.md](docs/testing.md) | Test coverage breakdown and gap analysis |
| [docs/deployment/environments.md](docs/deployment/environments.md) | Dev / staging / prod environment strategy |
| [docs/deployment/ci-cd.md](docs/deployment/ci-cd.md) | CI/CD pipeline reference |
| [docs/grafana/README.md](docs/grafana/README.md) | Grafana dashboard import guide |

---

## License

Source-available under the **Business Source License 1.1 (BUSL-1.1)**. The source is publicly visible for review and learning. Commercial use is not permitted until 2029-01-01, at which point the license converts to MIT. See [LICENSE](LICENSE) for full terms.
