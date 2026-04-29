#!/bin/sh
set -e

echo "Running Alembic migrations..."
if alembic upgrade head; then
    echo "Migrations complete."
else
    echo "WARNING: Alembic migrations failed — starting server to surface diagnostics via /health/ready."
fi

echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
