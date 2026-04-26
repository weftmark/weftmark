# weaving_site webhook server

Dev-only tool. Receives Gitea webhooks and invokes `claude -p` to act on events.

## Setup

```bash
# Create and activate the conda env
conda env create -f environment.yml
conda activate weaving_webhook

# Copy and fill in config
cp .env.example .env
# Edit .env — set WEBHOOK_SECRET, GITEA_TOKEN, REPO_PATH
```

## Running

```bash
conda activate weaving_webhook
cd tools/webhook_server
uvicorn main:app --reload
# or, to use the PORT from .env:
python main.py
```

Server starts on port 3001 (configurable via `PORT` in `.env`).

## Gitea webhook config

In Gitea → repo Settings → Webhooks → Add Webhook → Gitea:

- **Target URL**: `http://<your-machine-ip>:3001/webhook`
- **Secret**: must match `WEBHOOK_SECRET` in `.env`
- **Content type**: `application/json`
- **Events**: choose the events you want handled (e.g. Issue Comments)

## Supported events

| Event | Handler | Action |
|---|---|---|
| `issue_comment` | `handlers/issue_comment.py` | Runs `claude -p` with the comment context; posts response back to the issue |

## Adding a new event handler

1. Create `handlers/<event_name>.py` with an `async def handle(payload: dict)` function
2. Add it to the `HANDLERS` dict in `main.py`

## Files

```
tools/webhook_server/
├── main.py              # FastAPI app, HMAC validation, event routing
├── config.py            # Settings loaded from .env
├── claude_runner.py     # Runs claude -p as a subprocess
├── gitea.py             # Gitea API helpers (post comments, etc.)
├── handlers/
│   └── issue_comment.py # Handler for issue_comment events
├── environment.yml      # conda env spec (weaving_webhook)
├── .env.example         # Config template
└── README.md
```
